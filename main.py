"""Main FastAPI application for the productivity enforcement app."""

import atexit
import signal
import sys
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from ai_analyzer import ai_analyzer
from app_killer import app_killer
from blocker import block_sites, unblock_sites, are_sites_blocked, is_admin
from config import BLOCKED_SITES, BLOCKED_APPS, CONFIRMATION_PHRASE
from monitor import monitor
from state import app_state, Mode
from tts import tts


def cleanup():
    """Cleanup function to restore system state on exit."""
    print("\nCleaning up...")
    try:
        unblock_sites()
        app_killer.stop()
        monitor.stop()
        print("Cleanup complete.")
    except Exception as e:
        print(f"Cleanup error: {e}")


def on_analysis_ready(image):
    """Callback when captures are ready for AI analysis."""
    print("Analyzing captures...")
    result = ai_analyzer.analyze(image)
    if result:
        print(f"Analysis: productive={result.productive}, reason={result.reason}")
        if not result.productive:
            tts.speak_productivity_nudge(result.reason)


def on_mode_change(new_mode: Mode):
    """Callback when app mode changes."""
    if new_mode == Mode.ON:
        block_sites()
        app_killer.start()
        monitor.start()
        tts.speak_mode_change("on")
    elif new_mode == Mode.OFF:
        unblock_sites()
        app_killer.stop()
        monitor.stop()
        tts.speak_mode_change("off")
    elif new_mode == Mode.BREAK:
        unblock_sites()
        app_killer.stop()
        monitor.stop()
        tts.speak_mode_change("break")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Startup
    print("Starting Productivity Enforcer...")
    print(f"Running as admin: {is_admin()}")

    # Set up callbacks
    monitor.set_on_analysis_ready(on_analysis_ready)
    app_state.set_on_mode_change(on_mode_change)

    # Register cleanup
    atexit.register(cleanup)
    signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))
    signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))

    yield

    # Shutdown
    cleanup()


app = FastAPI(title="Deep Work Productivity Enforcer", lifespan=lifespan)
templates = Jinja2Templates(directory="templates")


class ModeRequest(BaseModel):
    mode: str
    confirmation: str = ""
    break_duration: int = 5


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Render the main dashboard."""
    recent_results = ai_analyzer.get_recent_results(10)

    # Format results for template
    formatted_results = []
    for r in reversed(recent_results):
        formatted_results.append({
            "productive": r.productive,
            "reason": r.reason,
            "timestamp": r.timestamp.strftime("%H:%M")
        })

    return templates.TemplateResponse("index.html", {
        "request": request,
        "mode": app_state.mode.value,
        "break_remaining": app_state.break_remaining_seconds,
        "confirmation_phrase": CONFIRMATION_PHRASE,
        "blocked_sites": [s for s in BLOCKED_SITES if not s.startswith("www.")],
        "blocked_apps": BLOCKED_APPS,
        "sites_blocked": are_sites_blocked(),
        "is_admin": is_admin(),
        "results": formatted_results
    })


@app.post("/api/mode")
async def set_mode(req: ModeRequest):
    """Change the app mode."""
    try:
        new_mode = Mode(req.mode.lower())
    except ValueError:
        return {"success": False, "error": f"Invalid mode: {req.mode}"}

    # Check confirmation phrase when turning off
    if new_mode == Mode.OFF and app_state.mode == Mode.ON:
        if req.confirmation != CONFIRMATION_PHRASE:
            return {"success": False, "error": "Incorrect confirmation phrase"}

    # Set the mode
    app_state.set_mode(new_mode, break_duration_minutes=req.break_duration)

    return {
        "success": True,
        "mode": app_state.mode.value,
        "break_remaining": app_state.break_remaining_seconds
    }


@app.get("/api/status")
async def get_status():
    """Get current app status."""
    return {
        "mode": app_state.mode.value,
        "break_remaining": app_state.break_remaining_seconds,
        "sites_blocked": are_sites_blocked(),
        "is_admin": is_admin()
    }


if __name__ == "__main__":
    import uvicorn

    print("""
╔═══════════════════════════════════════════════════════════╗
║           Deep Work - Productivity Enforcer                ║
║                                                           ║
║  IMPORTANT: Run this as Administrator for full features   ║
║                                                           ║
║  Open http://localhost:8000 in your browser               ║
╚═══════════════════════════════════════════════════════════╝
    """)

    uvicorn.run(app, host="0.0.0.0", port=8000)
