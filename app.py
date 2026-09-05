"""
Kisan Dost — web backend.

This is a thin wrapper around the SAME agent logic in main.py (tools, agents,
guardrails — nothing duplicated). It exposes one API endpoint the frontend
calls, and serves the chat page itself.

Run with:
    uvicorn app:app --reload
Then open:
    http://127.0.0.1:8000
"""

from __future__ import annotations

import asyncio
import traceback
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agents import (
    InputGuardrailTripwireTriggered,
    OutputGuardrailTripwireTriggered,
    Runner,
    SQLiteSession,
)

# Everything below is imported straight from your existing terminal app —
# main.py only *runs* the terminal loop inside `if __name__ == "__main__":`,
# so importing it here just reuses the agents/tools/guardrails without
# starting the terminal chat.
from main import FarmerProfile, triage_agent, run_config

app = FastAPI(title="Kisan Dost")

# This is a single-farmer local demo, so one shared profile + session is
# enough (same idea as the terminal version). Each browser tab talks to the
# same "farmer" — that's fine for a hackathon demo on your own machine.
farmer_profile = FarmerProfile()
web_session = SQLiteSession("kisan_dost_web_session")


class ChatRequest(BaseModel):
    message: str
    name: Optional[str] = None


class ChatResponse(BaseModel):
    reply: str
    blocked: bool = False
    district: Optional[str] = None
    season: Optional[str] = None
    water_availability: Optional[str] = None
    land_size_acres: Optional[float] = None


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    if req.name:
        farmer_profile.name = req.name

    try:
        result = await asyncio.wait_for(
            Runner.run(
                triage_agent,
                req.message,
                context=farmer_profile,
                session=web_session,
                run_config=run_config,
            ),
            timeout=45,
        )
        return ChatResponse(
            reply=str(result.final_output),
            district=farmer_profile.district,
            season=farmer_profile.season,
            water_availability=farmer_profile.water_availability,
            land_size_acres=farmer_profile.land_size_acres,
        )
    except InputGuardrailTripwireTriggered:
        return ChatResponse(
            reply=(
                "That's outside what I can help with — I'm a farm-advisory assistant "
                "for crops, pests, fertilizer, mandi prices, irrigation and government "
                "schemes. Please ask me something in that area."
            ),
            blocked=True,
        )
    except OutputGuardrailTripwireTriggered:
        return ChatResponse(
            reply=(
                "I can't share that response as-is because it failed a safety check "
                "(unsafe pesticide dosage or human-medical advice). Please rephrase your "
                "question, or consult your local agriculture extension office."
            ),
            blocked=True,
        )
    except asyncio.TimeoutError:
        return ChatResponse(
            reply=(
                "Gemini took too long to respond (45s timeout) — this usually means "
                "a network issue or the free-tier quota is being throttled. Please "
                "wait a moment and try again."
            ),
            blocked=True,
        )
    except Exception as e:
        # Catch-all so the server never hard-crashes the request and the
        # frontend never has to guess — print the full traceback to the
        # terminal for debugging, and tell the user something useful.
        traceback.print_exc()
        error_name = type(e).__name__
        if "RateLimit" in error_name or "429" in str(e):
            reply = (
                "Gemini's free-tier rate limit was hit — please wait 30-60 seconds "
                "and try again."
            )
        else:
            reply = f"[Server error: {error_name}] {e}"
        return ChatResponse(reply=reply, blocked=True)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse("static/index.html")


# Everything else in /static (style.css, script.js) is served as-is.
app.mount("/static", StaticFiles(directory="static"), name="static")
