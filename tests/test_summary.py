from tests.conftest import trip_payload


def test_daily_summary_calculates_totals_and_payment_breakdown(client):
    first = trip_payload()
    second = trip_payload(
        id="test-2",
        start="2026-10-01T09:05:00+04:00",
        end="2026-10-01T09:20:00+04:00",
        amount=1500,
        payment="cash",
        commission=225,
    )
    assert client.post("/api/trips", json=first).status_code == 201
    assert client.post("/api/trips", json=second).status_code == 201

    response = client.get("/api/summary?date=2026-10-01")
    assert response.status_code == 200
    assert response.json() == {
        "date": "2026-10-01",
        "trip_count": 2,
        "revenue": 3900.0,
        "commission": 585.0,
        "take_home": 3315.0,
        "cash": {"trip_count": 1, "amount": 1500.0},
        "card": {"trip_count": 1, "amount": 2400.0},
    }


def test_rejects_invalid_trip_data(client):
    bad_amount = client.post("/api/trips", json=trip_payload(amount=0))
    assert bad_amount.status_code == 422

    bad_time = client.post("/api/trips", json=trip_payload(
        start="2026-10-01T09:00:00+04:00",
        end="2026-10-01T08:00:00+04:00",
    ))
    assert bad_time.status_code == 422
