"""
Bonus: automated tests for the REST API layer.

Uses an in-memory SQLite DB (swapped in for Postgres) so the tests run
anywhere with zero setup:  cd backend && pytest
"""
import os
import sys

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("GROQ_API_KEY", "test-key")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import StaticPool

# --- build an isolated in-memory DB and monkeypatch it into the app -------
test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

from app import database  # noqa: E402

database.engine = test_engine
database.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

from app.main import app  # noqa: E402
from app.database import Base, get_db  # noqa: E402

Base.metadata.create_all(bind=test_engine)


def override_get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

SAMPLE_PATIENT = {
    "first_name": "Test",
    "last_name": "Patient",
    "date_of_birth": "1995-01-01",
    "sex": "Other",
    "phone_number": "5550001111",
    "address_line_1": "1 Test St",
    "city": "Testville",
    "state": "CA",
    "zip_code": "90001",
}


def test_create_and_get_patient():
    resp = client.post("/patients", json=SAMPLE_PATIENT)
    assert resp.status_code == 201
    body = resp.json()
    assert body["error"] is None
    patient_id = body["data"]["patient_id"]

    resp = client.get(f"/patients/{patient_id}")
    assert resp.status_code == 200
    assert resp.json()["data"]["last_name"] == "Patient"


def test_list_and_filter_by_last_name():
    resp = client.get("/patients", params={"last_name": "Patient"})
    assert resp.status_code == 200
    assert len(resp.json()["data"]) >= 1


def test_update_patient_partial():
    resp = client.post("/patients", json={**SAMPLE_PATIENT, "phone_number": "5550002222"})
    patient_id = resp.json()["data"]["patient_id"]

    resp = client.put(f"/patients/{patient_id}", json={"city": "New City"})
    assert resp.status_code == 200
    assert resp.json()["data"]["city"] == "New City"


def test_soft_delete_patient():
    resp = client.post("/patients", json={**SAMPLE_PATIENT, "phone_number": "5550003333"})
    patient_id = resp.json()["data"]["patient_id"]

    resp = client.delete(f"/patients/{patient_id}")
    assert resp.status_code == 200

    resp = client.get(f"/patients/{patient_id}")
    assert resp.status_code == 404  # soft-deleted, so it's invisible to GET


def test_get_nonexistent_patient_returns_404():
    resp = client.get("/patients/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


def test_invalid_patient_payload_returns_422():
    bad = {**SAMPLE_PATIENT, "sex": "Not A Real Value", "phone_number": "5550004444"}
    resp = client.post("/patients", json=bad)
    assert resp.status_code == 422
