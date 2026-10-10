from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path
import json
import os
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import Date, DateTime, Float, String, create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
STATIC_DIR = BASE_DIR / "app" / "static"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'driver_diary.db'}")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Trip(Base):
    __tablename__ = "trips"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    start: Mapped[str] = mapped_column(String(50), nullable=False)
    end: Mapped[str] = mapped_column(String(50), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    payment: Mapped[str] = mapped_column(String(10), nullable=False)
    commission: Mapped[float] = mapped_column(Float, nullable=False)
    day: Mapped[date] = mapped_column(Date, index=True, nullable=False)


class TripCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(min_length=1, max_length=100)
    start: datetime
    end: datetime
    amount: float = Field(gt=0, allow_inf_nan=False)
    payment: Literal["cash", "card"]
    commission: float = Field(ge=0, allow_inf_nan=False)

    @field_validator("start", "end")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Время должно содержать часовой пояс, например +04:00")
        return value

    @model_validator(mode="after")
    def validate_trip(self):
        if self.end <= self.start:
            raise ValueError("Время окончания должно быть позже времени начала")
        if self.commission > self.amount:
            raise ValueError("Комиссия не может превышать сумму поездки")
        return self


class TripOut(BaseModel):
    id: str
    start: datetime
    end: datetime
    amount: float
    payment: Literal["cash", "card"]
    commission: float


def get_trip_day(start: datetime) -> date:
    # День поездки определяется по календарной дате в часовом поясе,
    # переданном в поле start.
    return start.date()


def trip_to_dict(trip: Trip) -> dict:
    return {
        "id": trip.id,
        "start": trip.start,
        "end": trip.end,
        "amount": trip.amount,
        "payment": trip.payment,
        "commission": trip.commission,
    }


def seed_from_json(session: Session) -> None:
    source = DATA_DIR / "trips.json"
    if not source.exists():
        return
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
        for raw in payload:
            item = TripCreate.model_validate(raw)
            if session.get(Trip, item.id) is None:
                session.add(Trip(
                    id=item.id, start=item.start.isoformat(), end=item.end.isoformat(), amount=item.amount,
                    payment=item.payment, commission=item.commission,
                    day=get_trip_day(item.start),
                ))
        session.commit()
    except (ValueError, TypeError, IntegrityError):
        session.rollback()
        raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        seed_from_json(session)
    yield


app = FastAPI(
    title="Дневник смен водителя",
    description="API для учёта поездок и дневной выручки.",
    version="1.0.0",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/trips", response_model=list[TripOut])
def list_trips(day: date = Query(..., alias="date", description="Дата в формате YYYY-MM-DD")):
    with SessionLocal() as session:
        rows = session.scalars(select(Trip).where(Trip.day == day)).all()
        rows.sort(key=lambda row: (datetime.fromisoformat(row.start).astimezone().timestamp(), row.id))
        return [trip_to_dict(row) for row in rows]


@app.get("/api/summary")
def daily_summary(day: date = Query(..., alias="date", description="Дата в формате YYYY-MM-DD")):
    with SessionLocal() as session:
        trips = session.scalars(select(Trip).where(Trip.day == day)).all()

    cash = [trip for trip in trips if trip.payment == "cash"]
    card = [trip for trip in trips if trip.payment == "card"]
    revenue = round(sum(trip.amount for trip in trips), 2)
    commission = round(sum(trip.commission for trip in trips), 2)
    return {
        "date": day.isoformat(),
        "trip_count": len(trips),
        "revenue": revenue,
        "commission": commission,
        "take_home": round(revenue - commission, 2),
        "cash": {
            "trip_count": len(cash),
            "amount": round(sum(trip.amount for trip in cash), 2),
        },
        "card": {
            "trip_count": len(card),
            "amount": round(sum(trip.amount for trip in card), 2),
        },
    }


@app.post("/api/trips", response_model=TripOut, status_code=201)
def create_trip(payload: TripCreate):
    with SessionLocal() as session:
        existing = session.get(Trip, payload.id)
        if existing is not None:
            # Idempotency: exact retry returns the existing record; conflicting
            # content with the same ID is rejected instead of overwriting data.
            same = (
                datetime.fromisoformat(existing.start) == payload.start
                and datetime.fromisoformat(existing.end) == payload.end
                and existing.amount == payload.amount
                and existing.payment == payload.payment
                and existing.commission == payload.commission
            )
            if same:
                return trip_to_dict(existing)
            raise HTTPException(
                status_code=409,
                detail="Поездка с таким id уже существует, но данные отличаются",
            )

        trip = Trip(
            id=payload.id,
            start=payload.start.isoformat(),
            end=payload.end.isoformat(),
            amount=payload.amount,
            payment=payload.payment,
            commission=payload.commission,
            day=get_trip_day(payload.start),
        )
        session.add(trip)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            existing = session.get(Trip, payload.id)
            if existing is not None:
                raise HTTPException(status_code=409, detail="Поездка с таким id уже существует")
            raise HTTPException(status_code=409, detail="Не удалось сохранить поездку")
        session.refresh(trip)
        return trip_to_dict(trip)
