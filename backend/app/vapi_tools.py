"""
Handles Vapi "tool calls" (function calling). Vapi's own model (configured
directly on the Vapi assistant) runs the actual conversation - once it has
collected everything, it calls our `register_patient` tool with the
structured data as arguments. We validate everything server-side (same
validators.py used everywhere else) before ever writing to the database,
and return a short result string that Vapi reads back to the caller.
"""
import logging

from sqlalchemy.orm import Session

from app import crud
from app.schemas import PatientCreate, PatientUpdate
from app.validators import FIELD_VALIDATORS, REQUIRED_FIELDS, ALL_FIELDS

logger = logging.getLogger("voice_agent")


def register_patient_tool(args: dict, db: Session) -> str:
    """
    Validates every field the LLM sent, checks for a duplicate by phone
    number (updates instead of creating a second record if one exists),
    and returns a plain-English result string for the assistant to speak.
    """
    cleaned = {}
    for field in ALL_FIELDS:
        if field not in args or args[field] in (None, ""):
            continue
        validator = FIELD_VALIDATORS.get(field)
        if not validator:
            continue
        ok, value, reason = validator(args[field])
        if not ok:
            logger.info("register_patient validation failed for %s: %s", field, reason)
            return f"I couldn't save that - {reason} Please ask the caller again and retry."
        if value is not None:
            cleaned[field] = value.isoformat() if hasattr(value, "isoformat") else value

    missing = [f for f in REQUIRED_FIELDS if f not in cleaned]
    if missing:
        nice = ", ".join(m.replace("_", " ") for m in missing)
        return f"Missing required information: {nice}. Please collect that from the caller and call this tool again."

    try:
        existing = crud.get_patient_by_phone(db, cleaned["phone_number"])
        if existing:
            crud.update_patient(db, existing, PatientUpdate(**cleaned))
            return (
                f"Updated the existing record for {existing.first_name} {existing.last_name}. "
                f"Let the caller know their information has been updated."
            )
        created = crud.create_patient(db, PatientCreate(**cleaned))
        return (
            f"Successfully registered {created.first_name} {created.last_name}. "
            f"Let the caller know they're all set and thank them for calling."
        )
    except Exception:
        logger.exception("Failed to save patient via Vapi tool call")
        return (
            "There was a problem saving the record on our end. "
            "Apologize to the caller and ask them to call back in a few minutes."
        )


def lookup_patient_by_phone_tool(args: dict, db: Session) -> str:
    """Optional helper tool: lets the assistant check for an existing patient early in the call."""
    phone = args.get("phone_number", "")
    ok, cleaned_phone, reason = FIELD_VALIDATORS["phone_number"](phone)
    if not ok:
        return f"That phone number doesn't look valid - {reason}"
    existing = crud.get_patient_by_phone(db, cleaned_phone)
    if existing:
        return (
            f"Found an existing patient: {existing.first_name} {existing.last_name}, "
            f"born {existing.date_of_birth}. Ask if they'd like to update this record."
        )
    return "No existing patient found with that phone number. Proceed with new registration."