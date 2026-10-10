from tests.conftest import trip_payload


def test_exact_retry_does_not_create_duplicate(client):
    payload = trip_payload()
    first = client.post("/api/trips", json=payload)
    second = client.post("/api/trips", json=payload)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    trips = client.get("/api/trips?date=2026-10-01")
    assert trips.status_code == 200
    assert len(trips.json()) == 1


def test_same_id_with_different_data_returns_conflict(client):
    assert client.post("/api/trips", json=trip_payload()).status_code == 201
    response = client.post("/api/trips", json=trip_payload(amount=999))
    assert response.status_code == 409
    assert len(client.get("/api/trips?date=2026-10-01").json()) == 1
