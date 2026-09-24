"""
Run once after the database is set up to insert demo records:
    python seed.py
"""
from datetime import date

from app.database import SessionLocal, init_db
from app.models import Patient

init_db()
db = SessionLocal()

demo_patients = [
    Patient(
        first_name="Jane", last_name="Doe", date_of_birth=date(1990, 5, 14),
        sex="Female", phone_number="5551234567", email="jane.doe@example.com",
        address_line_1="123 Main St", city="Austin", state="TX", zip_code="73301",
        preferred_language="English",
    ),
    Patient(
        first_name="Carlos", last_name="Ramirez", date_of_birth=date(1985, 11, 2),
        sex="Male", phone_number="5559876543",
        address_line_1="456 Oak Ave", city="Phoenix", state="AZ", zip_code="85001",
        preferred_language="Spanish",
    ),
]

for p in demo_patients:
    exists = db.query(Patient).filter(Patient.phone_number == p.phone_number).first()
    if not exists:
        db.add(p)

db.commit()
db.close()
print("Seed data inserted.")
