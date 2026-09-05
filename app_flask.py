"""
Kisan Dost — Flask web backend (alternative to app.py / FastAPI).

Same agent logic from main.py, served with Flask instead of FastAPI+uvicorn.

Install Flask first:
    pip install flask

Run with:
    python app_flask.py
Then open:
    http://127.0.0.1:8000
"""

import asyncio
import traceback

from flask import Flask, request, jsonify, send_from_directory

from agents import (
    InputGuardrailTripwireTriggered,
    OutputGuardrailTripwireTriggered,
    Runner,
    SQLiteSession,
)

from main import FarmerProfile, triage_agent, run_config

app = Flask(__name__, static_folder="static", static_url_path="/static")

farmer_profile = FarmerProfile()
web_session = SQLiteSession("kisan_dost_web_session")


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/health")
def health():
    """Quick check: is the server up, and can it reach Gemini at all?
    Visit http://127.0.0.1:8000/api/health in your browser directly.
    """
    async def ping():
        return await asyncio.wait_for(
            Runner.run(triage_agent, "hello", run_config=run_config),
            timeout=20,
        )

    try:
        asyncio.run(ping())
        return jsonify({"status": "ok", "message": "Server and Gemini are both reachable."})
    except asyncio.TimeoutError:
        return jsonify({
            "status": "error",
            "message": "Timed out waiting for Gemini (20s). Likely a network/firewall block, or quota throttling.",
        }), 500
    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "message": f"{type(e).__name__}: {e}"}), 500


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(force=True) or {}
    message = data.get("message", "")
    name = data.get("name")

    if name:
        farmer_profile.name = name

    async def run_agent():
        return await asyncio.wait_for(
            Runner.run(
                triage_agent,
                message,
                context=farmer_profile,
                session=web_session,
                run_config=run_config,
            ),
            timeout=45,
        )

    try:
        result = asyncio.run(run_agent())
        return jsonify({
            "reply": str(result.final_output),
            "blocked": False,
            "district": farmer_profile.district,
            "season": farmer_profile.season,
            "water_availability": farmer_profile.water_availability,
            "land_size_acres": farmer_profile.land_size_acres,
        })
    except InputGuardrailTripwireTriggered:
        return jsonify({
            "reply": (
                "That's outside what I can help with — I'm a farm-advisory assistant "
                "for crops, pests, fertilizer, mandi prices, irrigation and government "
                "schemes. Please ask me something in that area."
            ),
            "blocked": True,
        })
    except OutputGuardrailTripwireTriggered:
        return jsonify({
            "reply": (
                "I can't share that response as-is because it failed a safety check "
                "(unsafe pesticide dosage or human-medical advice). Please rephrase your "
                "question, or consult your local agriculture extension office."
            ),
            "blocked": True,
        })
    except asyncio.TimeoutError:
        return jsonify({
            "reply": (
                "Gemini took too long to respond (45s timeout) — this usually means "
                "a network issue or the free-tier quota is being throttled. Please "
                "wait a moment and try again."
            ),
            "blocked": True,
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({
            "reply": f"[Server error: {type(e).__name__}] {e}",
            "blocked": True,
        })


if __name__ == "__main__":
    # threaded=True lets Flask handle the request without blocking everything
    # else while waiting on Gemini's API.
    app.run(host="127.0.0.1", port=8000, debug=True, threaded=True)
