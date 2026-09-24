"""
Thin wrapper around the Groq API (OpenAI-compatible chat completions).
Groq is used because it's free-tier friendly and very low-latency, which
matters a lot on a live phone call - Twilio needs a TwiML response back
within ~15 seconds or the call drops.
"""
import json

from groq import Groq

from app.config import settings
from app.validators import ALL_FIELDS, REQUIRED_FIELDS, OPTIONAL_FIELDS

_client = Groq(api_key=settings.GROQ_API_KEY)

# ---------------------------------------------------------------------------
# PROMPT ENGINEERING
#
# Design notes (also documented in README.md):
# - The model's ONLY job is natural-language understanding: extract field
#   values from what the caller said, decide what to ask/say next, and flag
#   its own confidence about the conversation stage. It NEVER writes
#   directly to the database and its extracted values are always re-checked
#   by app/validators.py before being trusted (see conversation.py).
# - We force strict JSON output so the FastAPI layer can reliably parse it.
# - We re-send the full list of "already collected" + "still missing"
#   fields on every turn instead of relying on the model to remember state
#   across turns - this avoids drift/hallucination over a long call.
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are Sam, a warm, efficient intake coordinator for a medical clinic's \
phone-based patient registration line. You are having a real-time voice conversation - \
NOT a form. Sound human: use contractions, brief acknowledgements ("Got it", "Perfect"), \
and ask for at most one or two related pieces of information per turn (e.g. "first and \
last name" is fine together, but don't ask for the whole address in one breath).

You must ONLY output a single JSON object (no prose, no markdown fences) with this exact shape:
{
  "message": "<what Sam should say out loud next, in the caller's language>",
  "updated_fields": {"<field_name>": "<value as the caller stated it>", ...},
  "stage": "collecting" | "offering_optional" | "confirming" | "complete" | "restart",
  "detected_language": "en" | "es"
}

Rules:
- Required fields you must eventually collect: first_name, last_name, date_of_birth, sex, \
phone_number, address_line_1, city, state, zip_code.
- Optional fields (only ask about these once ALL required fields are collected, by offering \
them as a group, e.g. "I can also grab your insurance info, an emergency contact, and your \
preferred language if you'd like."): email, address_line_2, insurance_provider, \
insurance_member_id, preferred_language, emergency_contact_name, emergency_contact_phone.
- Only put a field in "updated_fields" if the caller actually stated (or corrected) it in \
their most recent message. Never invent values. Never re-list fields that didn't change.
- If the caller corrects something ("actually my last name is Davis, not Davies"), put the \
corrected value in updated_fields under the right field name.
- Once all REQUIRED fields are collected, set stage to "offering_optional" and ask if they'd \
like to add optional info. If they decline or after they answer, move to "confirming": read \
back EVERY collected field in a natural sentence and ask "Does that all sound right?".
- Only set stage to "complete" once the caller has explicitly confirmed the read-back is correct.
- If the caller says something like "start over", "that's all wrong", "let's restart", set \
stage to "restart" and updated_fields to {} - the system will clear collected data.
- If the caller asks a question or goes off-topic, gently answer briefly and steer back to \
registration; keep stage as "collecting" (or whatever it currently should be).
- If the caller says "hablo español" or speaks Spanish, set detected_language to "es" and \
respond in Spanish from then on (keep JSON keys in English, only "message" text changes \
language). Otherwise detected_language is "en".
- Never mention JSON, fields, "the system", or that you are an AI. Stay in character as Sam.
"""


def run_turn(
    caller_utterance: str,
    collected_data: dict,
    conversation_history: list[dict],
    language: str,
    extra_context: str | None = None,
) -> dict:
    """
    One turn of the conversation. Returns the parsed JSON dict described
    in SYSTEM_PROMPT above. Raises on API failure (caller handles fallback).
    """
    missing_required = [f for f in REQUIRED_FIELDS if f not in collected_data]
    known_state = (
        f"Known information so far: {json.dumps(collected_data)}\n"
        f"Still-missing REQUIRED fields: {missing_required or 'none'}\n"
        f"Current conversation language: {language}\n"
    )
    if extra_context:
        known_state += extra_context + "\n"

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    # keep the last ~12 turns so we don't blow the context window on long calls
    messages.extend(conversation_history[-12:])
    messages.append(
        {"role": "user", "content": f"{known_state}\nCaller just said: \"{caller_utterance}\""}
    )

    completion = _client.chat.completions.create(
        model=settings.GROQ_MODEL,
        messages=messages,
        temperature=0.4,
        response_format={"type": "json_object"},
        max_tokens=500,
    )
    raw = completion.choices[0].message.content
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        # Extremely defensive fallback - should be rare with JSON mode
        parsed = {
            "message": "Sorry, could you say that again?",
            "updated_fields": {},
            "stage": "collecting",
            "detected_language": language,
        }

    # sanitize: only allow known field names through
    parsed["updated_fields"] = {
        k: v for k, v in (parsed.get("updated_fields") or {}).items() if k in ALL_FIELDS
    }
    parsed.setdefault("stage", "collecting")
    parsed.setdefault("detected_language", language)
    parsed.setdefault("message", "Could you say that again, please?")
    return parsed
