"""
Orchestrates one turn of the phone conversation:

  Twilio speech text --> Groq (NLU + next message) --> code-level validation
  --> merge into persisted CallSession.collected_data --> maybe write Patient
  --> the message to speak back to the caller

Every field Groq claims to have extracted is re-validated in Python before
it is trusted (see validators.py) - if a field fails validation we DISCARD
the model's message for that field and deterministically ask again, so a
confused/hallucinating model can never save bad data.
"""
import logging

from sqlalchemy.orm import Session

from app import crud, groq_service
from app.models import CallSession
from app.schemas import PatientCreate, PatientUpdate
from app.validators import FIELD_VALIDATORS, REQUIRED_FIELDS

logger = logging.getLogger("voice_agent")

GREETING_EN = (
    "Hi there, thanks for calling! I'm Sam, and I'll help you get registered today - "
    "it only takes a couple of minutes. Could I start with your first and last name?"
)
GREETING_ES = (
    "Hola, gracias por llamar. Soy Sam y te ayudare a registrarte hoy - "
    "solo toma un par de minutos. Podrias darme tu nombre y apellido para empezar?"
)


def _json_safe(value):
    """collected_data is stored as JSON - dates need to become strings."""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def start_call(db: Session, call_sid: str, caller_phone: str, initial_language: str = "en") -> tuple[CallSession, str]:
    session = CallSession(
        call_sid=call_sid,
        caller_phone=caller_phone,
        language=initial_language,
        stage="collecting",
        status="in_progress",
        collected_data={},
        conversation_history=[],
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    greeting = GREETING_EN if initial_language == "en" else GREETING_ES
    session.conversation_history = [{"role": "assistant", "content": greeting}]
    db.commit()
    return session, greeting


def handle_no_speech(db: Session, session: CallSession) -> tuple[str, bool]:
    """Caller was silent / Twilio couldn't transcribe. Returns (message, should_hangup)."""
    retries = int(session.silence_retries or "0") + 1
    session.silence_retries = str(retries)
    db.commit()
    if retries >= 3:
        return (
            "I'm having trouble hearing you, so I'll let you go for now - "
            "please call back when you have a clearer line. Goodbye!",
            True,
        )
    msg = (
        "Sorry, I didn't catch that." if session.language == "en"
        else "Perdon, no te escuche bien."
    ) + (" Could you say that again?" if session.language == "en" else " Puedes repetirlo?")
    return msg, False


def handle_turn(db: Session, session: CallSession, caller_utterance: str) -> tuple[str, bool]:
    """
    Runs one full turn. Returns (message_to_speak, should_hangup).
    """
    session.silence_retries = "0"

    extra_context = None
    if session.existing_patient_id:
        extra_context = (
            "NOTE: We already matched this caller's phone number to an existing patient "
            "record. You are currently confirming whether they want to UPDATE that record. "
            "Do not create a duplicate."
        )

    try:
        result = groq_service.run_turn(
            caller_utterance=caller_utterance,
            collected_data=session.collected_data,
            conversation_history=session.conversation_history,
            language=session.language,
            extra_context=extra_context,
        )
    except Exception:
        logger.exception("Groq call failed")
        return (
            "Sorry, I'm having a little trouble understanding right now. Could you repeat that?",
            False,
        )

    # persist the raw turn for transcript / debugging
    history = list(session.conversation_history)
    history.append({"role": "user", "content": caller_utterance})

    if result["detected_language"] in ("en", "es"):
        session.language = result["detected_language"]

    # --- restart handling -------------------------------------------------
    if result["stage"] == "restart":
        session.collected_data = {}
        session.stage = "collecting"
        message = result["message"]
        history.append({"role": "assistant", "content": message})
        session.conversation_history = history
        db.commit()
        return message, False

    # --- validate every field the model claims to have extracted ----------
    reprompt_reason = None
    collected = dict(session.collected_data)
    for field, raw_value in result["updated_fields"].items():
        validator = FIELD_VALIDATORS.get(field)
        if not validator:
            continue
        ok, cleaned, reason = validator(raw_value)
        if ok:
            collected[field] = _json_safe(cleaned)
        else:
            reprompt_reason = reason  # last invalid field wins; keep it simple
    session.collected_data = collected

    # --- duplicate-detection bonus -----------------------------------------
    if (
        "phone_number" in result["updated_fields"]
        and not session.existing_patient_id
        and not session.result_patient_id
    ):
        phone = collected.get("phone_number")
        if phone:
            existing = crud.get_patient_by_phone(db, phone)
            if existing:
                session.existing_patient_id = existing.patient_id
                msg = (
                    f"It looks like we already have a record for "
                    f"{existing.first_name} {existing.last_name}. Would you like to update "
                    f"that information instead of creating a new record?"
                )
                history.append({"role": "assistant", "content": msg})
                session.conversation_history = history
                db.commit()
                return msg, False

    # --- if code-level validation failed, override the model's message ----
    if reprompt_reason:
        session.stage = "collecting" if session.stage != "confirming" else "collecting"
        message = reprompt_reason
        history.append({"role": "assistant", "content": message})
        session.conversation_history = history
        db.commit()
        return message, False

    session.stage = result["stage"]
    message = result["message"]

    # --- completion: double-check required fields before ever saving ------
    if session.stage == "complete":
        missing = [f for f in REQUIRED_FIELDS if f not in session.collected_data]
        if missing:
            session.stage = "collecting"
            message = (
                f"Before I save this, I still need your {missing[0].replace('_', ' ')}. "
                f"Could you give me that?"
            )
        else:
            message, hangup = _save_patient(db, session, message)
            history.append({"role": "assistant", "content": message})
            session.conversation_history = history
            db.commit()
            return message, hangup

    history.append({"role": "assistant", "content": message})
    session.conversation_history = history
    db.commit()
    return message, False


def _save_patient(db: Session, session: CallSession, confirmation_message: str) -> tuple[str, bool]:
    try:
        data = dict(session.collected_data)
        if session.existing_patient_id:
            patient = crud.get_patient(db, session.existing_patient_id)
            if patient:
                crud.update_patient(db, patient, PatientUpdate(**data))
                session.result_patient_id = patient.patient_id
            else:
                created = crud.create_patient(db, PatientCreate(**data))
                session.result_patient_id = created.patient_id
        else:
            created = crud.create_patient(db, PatientCreate(**data))
            session.result_patient_id = created.patient_id

        session.status = "completed"
        first_name = data.get("first_name", "there")
        message = confirmation_message or f"You're all set, {first_name}. Thanks for calling, and take care!"
        return message, True
    except Exception:
        logger.exception("Failed to save patient record for call %s", session.call_sid)
        session.status = "in_progress"  # allow a retry if they call again
        return (
            "I'm sorry, I'm having trouble saving your information right now. "
            "Please try calling back in a few minutes. Goodbye.",
            True,
        )
