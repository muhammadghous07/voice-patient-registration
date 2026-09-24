import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    String,
    Date,
    DateTime,
    JSON,
    Text,
    TypeDecorator,
    CHAR,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from app.database import Base


def _now():
    return datetime.now(timezone.utc)


class GUID(TypeDecorator):
    """
    Platform-independent UUID column: uses Postgres's native UUID type in
    production, and a plain CHAR(36) in SQLite (used by the test suite).
    """

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return str(value)
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


class Patient(Base):
    __tablename__ = "patients"

    patient_id = Column(GUID(), primary_key=True, default=uuid.uuid4)

    first_name = Column(String(50), nullable=False)
    last_name = Column(String(50), nullable=False)
    date_of_birth = Column(Date, nullable=False)
    sex = Column(String(20), nullable=False)  # Male / Female / Other / Decline to Answer
    phone_number = Column(String(10), nullable=False, index=True)  # 10 digits, no formatting
    email = Column(String(255), nullable=True)

    address_line_1 = Column(String(255), nullable=False)
    address_line_2 = Column(String(255), nullable=True)
    city = Column(String(100), nullable=False)
    state = Column(String(2), nullable=False)
    zip_code = Column(String(10), nullable=False)

    insurance_provider = Column(String(255), nullable=True)
    insurance_member_id = Column(String(100), nullable=True)
    preferred_language = Column(String(50), nullable=False, default="English")

    emergency_contact_name = Column(String(100), nullable=True)
    emergency_contact_phone = Column(String(10), nullable=True)

    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)  # soft delete


class CallSession(Base):
    """
    One row per phone call. Holds the in-progress (or finished) conversation
    state so the agent can be stateless between HTTP requests - Twilio calls
    our webhook once per turn, so we reload state from here every time.
    """

    __tablename__ = "call_sessions"

    call_sid = Column(String(64), primary_key=True)
    caller_phone = Column(String(20), nullable=True)

    language = Column(String(5), nullable=False, default="en")  # "en" or "es"
    stage = Column(String(30), nullable=False, default="collecting")
    status = Column(String(20), nullable=False, default="in_progress")  # in_progress / completed / abandoned

    collected_data = Column(JSON, nullable=False, default=dict)
    conversation_history = Column(JSON, nullable=False, default=list)  # [{"role": "...", "content": "..."}]
    silence_retries = Column(String(5), nullable=False, default="0")

    existing_patient_id = Column(GUID(), nullable=True)  # set if duplicate-detection matched
    result_patient_id = Column(GUID(), nullable=True)  # set once a patient record is saved

    transcript_summary = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)
