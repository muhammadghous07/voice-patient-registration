import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.routers import patients, voice

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()  # cheap no-op if tables already exist; safe to run on every cold start
    yield


app = FastAPI(title="Voice AI Patient Registration", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Sabhi origins ko allow karne ke liye
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(patients.router)
app.include_router(voice.router)


@app.get("/")
def health():
    return {"status": "ok", "service": "voice-patient-registration"}