import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app import crud
from app.database import get_db
from app.schemas import PatientCreate, PatientOut, PatientUpdate, Envelope

router = APIRouter(prefix="/patients", tags=["patients"])


@router.get("", response_model=Envelope)
def list_patients(
    last_name: str | None = Query(None),
    date_of_birth: date | None = Query(None),
    phone_number: str | None = Query(None),
    db: Session = Depends(get_db),
):
    patients = crud.list_patients(db, last_name=last_name, date_of_birth=date_of_birth, phone_number=phone_number)
    data = [PatientOut.model_validate(p).model_dump(mode="json") for p in patients]
    return Envelope(data=data, error=None)


@router.get("/{patient_id}", response_model=Envelope)
def get_patient(patient_id: uuid.UUID, db: Session = Depends(get_db)):
    patient = crud.get_patient(db, patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return Envelope(data=PatientOut.model_validate(patient).model_dump(mode="json"), error=None)


@router.post("", response_model=Envelope, status_code=201)
def create_patient(payload: PatientCreate, db: Session = Depends(get_db)):
    try:
        patient = crud.create_patient(db, payload)
    except Exception as exc:  # duplicate phone, DB constraint, etc.
        raise HTTPException(status_code=400, detail=str(exc))
    return Envelope(data=PatientOut.model_validate(patient).model_dump(mode="json"), error=None)


@router.put("/{patient_id}", response_model=Envelope)
def update_patient(patient_id: uuid.UUID, payload: PatientUpdate, db: Session = Depends(get_db)):
    patient = crud.get_patient(db, patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    try:
        patient = crud.update_patient(db, patient, payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return Envelope(data=PatientOut.model_validate(patient).model_dump(mode="json"), error=None)


@router.delete("/{patient_id}", response_model=Envelope)
def delete_patient(patient_id: uuid.UUID, db: Session = Depends(get_db)):
    patient = crud.get_patient(db, patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    patient = crud.soft_delete_patient(db, patient)
    return Envelope(data={"patient_id": str(patient.patient_id), "deleted_at": patient.deleted_at.isoformat()}, error=None)
