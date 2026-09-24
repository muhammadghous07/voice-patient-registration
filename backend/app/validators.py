"""
Deterministic, code-level validation for every patient field.

Important: the PDF spec explicitly says "Validate all inputs server-side
(do not rely solely on the voice agent for validation)". The LLM extracts
values from natural speech, but every value is re-checked here before it's
ever written to collected_data or the database. If a value fails validation
we return (False, reason) and the conversation layer re-prompts the caller
for that specific field instead of trusting the model.
"""
import re
from datetime import date, datetime
from dateutil import parser as dateparser

US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL",
    "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT",
    "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI",
    "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC",
}

SEX_SYNONYMS = {
    "male": "Male", "m": "Male", "man": "Male",
    "female": "Female", "f": "Female", "woman": "Female",
    "other": "Other", "non-binary": "Other", "nonbinary": "Other",
    "decline to answer": "Decline to Answer", "decline": "Decline to Answer",
    "prefer not to say": "Decline to Answer", "rather not say": "Decline to Answer",
}

NAME_RE = re.compile(r"^[A-Za-z'\-\s]{1,50}$")
ZIP_RE = re.compile(r"^\d{5}(-\d{4})?$")


def validate_name(value: str):
    value = (value or "").strip()
    if not value or not NAME_RE.match(value):
        return False, None, "That name doesn't look right - it should only contain letters, hyphens or apostrophes."
    return True, value, None


def validate_dob(value: str):
    if not value:
        return False, None, "I didn't catch a date of birth."
    try:
        parsed = dateparser.parse(str(value), fuzzy=True, dayfirst=False).date()
    except (ValueError, OverflowError):
        return False, None, "That date of birth doesn't look valid. Could you say it again, like month, day, then year?"
    if parsed > date.today():
        return False, None, "That date of birth is in the future - could you double check it and tell me again?"
    if parsed.year < 1900:
        return False, None, "That date of birth seems too far back - could you say it again?"
    return True, parsed, None


def validate_sex(value: str):
    key = (value or "").strip().lower()
    if key in SEX_SYNONYMS:
        return True, SEX_SYNONYMS[key], None
    return False, None, "Could you tell me your sex as male, female, other, or decline to answer?"


def validate_us_phone(value: str):
    digits = re.sub(r"\D", "", value or "")
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        return False, None, "That doesn't look like a valid 10-digit US phone number. Could you repeat it slowly?"
    return True, digits, None


def validate_email(value: str):
    value = (value or "").strip()
    if not value:
        return True, None, None  # optional field
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", value):
        return False, None, "That email address doesn't look right - could you spell it out for me?"
    return True, value, None


def validate_state(value: str):
    key = (value or "").strip().upper()
    # accept full state names too (best-effort) by taking first 2 letters if already an abbreviation
    if key in US_STATES:
        return True, key, None
    return False, None, "That doesn't look like a valid US state abbreviation - which state are you in?"


def validate_zip(value: str):
    value = (value or "").strip()
    if not ZIP_RE.match(value):
        return False, None, "That zip code doesn't look right - could you repeat your 5-digit zip code?"
    return True, value, None


def validate_free_text(value: str, field_label: str, max_len: int = 255, required: bool = True):
    value = (value or "").strip()
    if not value and required:
        return False, None, f"I didn't catch your {field_label}."
    if len(value) > max_len:
        return False, None, f"That {field_label} seems too long - could you shorten it?"
    return True, (value or None), None


# Field -> validator function. Used by the conversation layer to check
# every field the LLM claims to have extracted this turn.
FIELD_VALIDATORS = {
    "first_name": validate_name,
    "last_name": validate_name,
    "date_of_birth": validate_dob,
    "sex": validate_sex,
    "phone_number": validate_us_phone,
    "email": validate_email,
    "address_line_1": lambda v: validate_free_text(v, "street address"),
    "address_line_2": lambda v: validate_free_text(v, "apartment or suite", required=False),
    "city": lambda v: validate_free_text(v, "city", max_len=100),
    "state": validate_state,
    "zip_code": validate_zip,
    "insurance_provider": lambda v: validate_free_text(v, "insurance provider", required=False),
    "insurance_member_id": lambda v: validate_free_text(v, "insurance member ID", required=False),
    "preferred_language": lambda v: validate_free_text(v, "preferred language", required=False),
    "emergency_contact_name": lambda v: validate_free_text(v, "emergency contact name", required=False),
    "emergency_contact_phone": validate_us_phone,
}

REQUIRED_FIELDS = [
    "first_name", "last_name", "date_of_birth", "sex", "phone_number",
    "address_line_1", "city", "state", "zip_code",
]

OPTIONAL_FIELDS = [
    "email", "address_line_2", "insurance_provider", "insurance_member_id",
    "preferred_language", "emergency_contact_name", "emergency_contact_phone",
]

ALL_FIELDS = REQUIRED_FIELDS + OPTIONAL_FIELDS
