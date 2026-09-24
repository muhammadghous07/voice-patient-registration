import json
import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app import vapi_tools
from app.database import get_db

logger = logging.getLogger("voice_agent")
router = APIRouter(prefix="/voice", tags=["voice"])

TOOL_HANDLERS = {
    "register_patient": vapi_tools.register_patient_tool,
    "lookup_patient_by_phone": vapi_tools.lookup_patient_by_phone_tool,
}


@router.post("/webhook")
async def vapi_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Single webhook endpoint for everything Vapi sends us. The important
    path is "tool-calls": Vapi's own model (system prompt + GPT-4.1,
    configured directly in the Vapi dashboard) runs the conversation, and
    calls our tools (see app/vapi_tools.py) once it has the data it needs.
    Every other message type is just logged - useful for debugging in the
    terminal while testing.
    """
    try:
        body = await request.json()
    except Exception:
        logger.warning("Vapi webhook got non-JSON body")
        return {"status": "ignored"}

    message = body.get("message", {}) or {}
    message_type = message.get("type")
    logger.info("Vapi webhook received message type=%s", message_type)

    if message_type == "tool-calls":
        tool_calls = message.get("toolCallList") or message.get("toolCalls") or []
        results = []
        for call in tool_calls:
            fn = call.get("function", {}) or {}
            name = fn.get("name")
            raw_args = fn.get("arguments", {})
            if isinstance(raw_args, str):
                try:
                    raw_args = json.loads(raw_args)
                except json.JSONDecodeError:
                    raw_args = {}

            handler = TOOL_HANDLERS.get(name)
            if handler:
                logger.info("Running tool '%s' with args: %s", name, raw_args)
                result_text = handler(raw_args, db)
            else:
                logger.warning("Unknown tool requested: %s", name)
                result_text = f"Unknown tool: {name}"

            results.append({"toolCallId": call.get("id"), "result": result_text})

        return {"results": results}

    if message_type == "end-of-call-report":
        logger.info("Call ended: %s", message.get("endedReason"))
        return {"status": "ack"}

    # transcript / status-update / speech-update / conversation-update etc:
    # nothing to do, just acknowledge so Vapi doesn't retry.
    return {"status": "ok"}