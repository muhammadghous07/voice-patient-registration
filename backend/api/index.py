"""
Vercel's Python runtime auto-detects a top-level `app` variable exposing a
WSGI/ASGI application in any file under /api. We just re-export the real
FastAPI app so the project structure stays clean (app/ has all the logic).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app  # noqa: F401,E402
