"""
Kisan Dost ("Farmer's Friend") — AI Agronomy Assistant
========================================================
Core agent logic shared by both the terminal app (this file's __main__ block)
and the web app (app.py imports `FarmerProfile`, `triage_agent`, and
`run_config` from here).

Runs on Google Gemini's free tier via Gemini's OpenAI-compatible endpoint,
using the OpenAI Agents SDK.
"""

import os
import asyncio
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv
from openai import AsyncOpenAI

from agents import (
    Agent,
    Runner,
    RunConfig,
    function_tool,
    ModelSettings,
    OpenAIChatCompletionsModel,
    input_guardrail,
    output_guardrail,
    GuardrailFunctionOutput,
    RunContextWrapper,
)

# ---------------------------------------------------------------------------
# 1. Load environment variables and configure the Gemini client
# ---------------------------------------------------------------------------

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

if not GEMINI_API_KEY:
    raise RuntimeError(
        "GEMINI_API_KEY is not set. Copy .env.example to .env and paste your "
        "key from https://aistudio.google.com/apikey"
    )

# Gemini speaks the OpenAI Chat Completions API, so we point the Agents SDK
# at Gemini's OpenAI-compatible base URL instead of OpenAI's servers.
gemini_client = AsyncOpenAI(api_key=GEMINI_API_KEY, base_url=GEMINI_BASE_URL)

gemini_model = OpenAIChatCompletionsModel(
    model=GEMINI_MODEL_NAME,
    openai_client=gemini_client,
)

# Gemini's OpenAI-compat layer rejects the "verbosity" field the SDK sends by
# default — this ModelSettings is reused on every single agent below to
# avoid the "Unknown name 'verbosity'" 400 error.
GEMINI_SAFE_SETTINGS = ModelSettings(verbosity=None)

run_config = RunConfig(model=gemini_model, model_provider=gemini_client)


# ---------------------------------------------------------------------------
# 2. Farmer profile (shared context object)
# ---------------------------------------------------------------------------

@dataclass
class FarmerProfile:
    """Holds what we know about the farmer so far. Passed as the run context
    so tools can read/update it, and the web app (app.py) can read it back
    to fill in the sidebar."""
    name: Optional[str] = None
    district: Optional[str] = None
    land_size_acres: Optional[float] = None
    season: Optional[str] = None                # "Rabi" or "Kharif"
    water_availability: Optional[str] = None


# ---------------------------------------------------------------------------
# 3. Tools (8 total: 7 domain tools + 1 profile-intake tool)
# ---------------------------------------------------------------------------

def _update_farmer_profile_impl(
    ctx: RunContextWrapper[FarmerProfile],
    name: Optional[str] = None,
    district: Optional[str] = None,
    land_size_acres: Optional[float] = None,
    season: Optional[str] = None,
    water_availability: Optional[str] = None,
) -> str:
    profile = ctx.context
    if name:
        profile.name = name
    if district:
        profile.district = district
    if land_size_acres is not None:
        profile.land_size_acres = land_size_acres
    if season:
        profile.season = season
    if water_availability:
        profile.water_availability = water_availability
    return "Farmer profile updated."


@function_tool
def update_farmer_profile(
    ctx: RunContextWrapper[FarmerProfile],
    name: Optional[str] = None,
    district: Optional[str] = None,
    land_size_acres: Optional[float] = None,
    season: Optional[str] = None,
    water_availability: Optional[str] = None,
) -> str:
    """Save/update known details about the farmer. Call this as soon as the
    farmer gives their name, district, land size, season, or water
    availability — even if only one detail is given at a time.

    Args:
        name: farmer's name, if given.
        district: farmer's district/region, if given.
        land_size_acres: land size in acres, if given.
        season: "Rabi" or "Kharif", if given.
        water_availability: e.g. "low", "medium", "high", if given.
    """
    return _update_farmer_profile_impl(
        ctx, name, district, land_size_acres, season, water_availability
    )


@function_tool
def update_profile(
    ctx: RunContextWrapper[FarmerProfile],
    name: Optional[str] = None,
    district: Optional[str] = None,
    land_size_acres: Optional[float] = None,
    season: Optional[str] = None,
    water_availability: Optional[str] = None,
) -> str:
    """Alias for update_farmer_profile — same behavior, shorter name. Gemini
    sometimes calls tools by a shortened name; registering both means the
    call succeeds either way instead of raising a ModelBehaviorError.

    Args:
        name: farmer's name, if given.
        district: farmer's district/region, if given.
        land_size_acres: land size in acres, if given.
        season: "Rabi" or "Kharif", if given.
        water_availability: e.g. "low", "medium", "high", if given.
    """
    return _update_farmer_profile_impl(
        ctx, name, district, land_size_acres, season, water_availability
    )


@function_tool
def crop_advisor(soil_type: str, region: str, season: str) -> str:
    """Suggest suitable crops for a given soil type, region, and season in Pakistan.

    Args:
        soil_type: e.g. "clay", "sandy", "loamy", "silty".
        region: district or province, e.g. "Multan, Punjab".
        season: "Rabi" (winter) or "Kharif" (summer), or a month name.
    """
    return (
        f"[Crop Advisor] For {soil_type} soil in {region} during {season}: "
        "recommend consulting local agri-extension data, but generally wheat "
        "and mustard suit Rabi season, while cotton, rice, and sugarcane suit "
        "Kharif season in most Punjab/Sindh soils. Rotate crops to preserve "
        "soil nutrients and consider water availability before final selection."
    )


@function_tool
def fertilizer_calculator(crop: str, area_acres: float, soil_nutrient_level: str) -> str:
    """Estimate fertilizer (NPK) quantities needed for a crop and field size.

    Args:
        crop: crop name, e.g. "wheat", "cotton", "rice".
        area_acres: field size in acres.
        soil_nutrient_level: "low", "medium", or "high".
    """
    base_rates = {"low": 1.2, "medium": 1.0, "high": 0.75}
    multiplier = base_rates.get(soil_nutrient_level.lower(), 1.0)
    urea = round(50 * area_acres * multiplier, 1)
    dap = round(25 * area_acres * multiplier, 1)
    sop = round(15 * area_acres * multiplier, 1)
    return (
        f"[Fertilizer Calculator] For {area_acres} acres of {crop} with "
        f"{soil_nutrient_level} soil nutrients: approx {urea} kg Urea, "
        f"{dap} kg DAP, {sop} kg SOP (potash). Split nitrogen application "
        "across 2-3 doses through the growing season rather than all at once."
    )


@function_tool
def irrigation_weather_advisor(region: str, crop_stage: str) -> str:
    """Give irrigation timing guidance based on region and crop growth stage.

    Args:
        region: district or province.
        crop_stage: e.g. "sowing", "vegetative", "flowering", "grain-filling".
    """
    return (
        f"[Irrigation & Weather Advisor] For {region} at the {crop_stage} "
        "stage: check local weather forecasts before irrigating to avoid "
        "waterlogging after rain. Critical watering stages are generally "
        "flowering and grain-filling — do not let the crop stress for water "
        "during these windows. Use canal/tube-well timing efficiently during "
        "peak summer heat (early morning or evening)."
    )


@function_tool
def pest_disease_doctor(crop: str, symptoms: str) -> str:
    """Diagnose likely pest/disease issues from described symptoms and give
    general, safety-conscious treatment guidance (not exact chemical dosages).

    Args:
        crop: affected crop name.
        symptoms: description of what the farmer is observing (e.g. "yellow
            spots on leaves", "holes in leaves", "wilting").
    """
    return (
        f"[Pest & Disease Doctor] For {crop} showing '{symptoms}': this "
        "pattern is commonly associated with fungal leaf spot or insect "
        "larvae feeding, depending on season. Recommend removing and "
        "destroying visibly infected leaves, improving field drainage, and "
        "consulting your nearest agriculture extension office or a licensed "
        "agri-dealer for the correct approved pesticide and dosage for your "
        "specific crop and region — do not apply chemicals without checking "
        "the product label and local recommended rate."
    )


@function_tool
def mandi_price_lookup(crop: str, market: str) -> str:
    """Look up an indicative mandi (market) price range for a crop.

    Args:
        crop: crop name.
        market: mandi/market name or city.
    """
    return (
        f"[Mandi Price Lookup] Indicative prices for {crop} at {market} "
        "mandi fluctuate daily — check the Agriculture Marketing Information "
        "Service (AMIS) portal or your local mandi committee board for "
        "today's confirmed rate before selling, since prices can move "
        "significantly within the same week."
    )


@function_tool
def govt_support_finder(topic: str, province: str) -> str:
    """Point to relevant government agricultural support schemes.

    Args:
        topic: e.g. "subsidy", "loan", "seed support", "tractor scheme".
        province: e.g. "Punjab", "Sindh", "KPK", "Balochistan".
    """
    return (
        f"[Govt Support Finder] For {topic} in {province}: check the "
        "provincial Agriculture Department portal and the Kissan Card / "
        "Kissan Package schemes (availability varies by province and year). "
        "The Pakistan Agricultural Research Council (PARC) and Zarai "
        "Taraqiati Bank Limited (ZTBL) are also good starting points for "
        "loans and subsidy programs."
    )


@function_tool
def profit_estimator(crop: str, area_acres: float, expected_yield_per_acre: float,
                      cost_per_acre: float, price_per_unit: float) -> str:
    """Estimate rough profit/loss for a crop cycle.

    Args:
        crop: crop name.
        area_acres: field size in acres.
        expected_yield_per_acre: expected yield per acre (in maunds or kg — be consistent).
        cost_per_acre: total input cost per acre (seed, fertilizer, labor, water).
        price_per_unit: expected sale price per unit of yield.
    """
    total_yield = area_acres * expected_yield_per_acre
    revenue = total_yield * price_per_unit
    total_cost = area_acres * cost_per_acre
    profit = revenue - total_cost
    return (
        f"[Profit Estimator] {crop} on {area_acres} acres: estimated revenue "
        f"~{revenue:,.0f}, estimated cost ~{total_cost:,.0f}, estimated "
        f"profit/loss ~{profit:,.0f} (before accounting for price fluctuation "
        "or weather risk — treat this as a rough planning estimate only)."
    )


# ---------------------------------------------------------------------------
# 4. Guardrails
# ---------------------------------------------------------------------------

class TopicCheckOutput:
    def __init__(self, is_farming_related: bool, reasoning: str):
        self.is_farming_related = is_farming_related
        self.reasoning = reasoning


def _extract_latest_user_text(input_data) -> str:
    """Guardrails may receive either a plain string (terminal loop, no
    session) or the full structured conversation input list (web app, since
    SQLiteSession reconstructs history including prior tool calls/results).
    We only want the farmer's latest plain message text here, so we never
    forward tool-call history into the tool-less topic-checker agent."""
    if isinstance(input_data, str):
        return input_data
    if isinstance(input_data, list):
        for item in reversed(input_data):
            if isinstance(item, dict) and item.get("role") == "user":
                content = item.get("content")
                if isinstance(content, str):
                    return content
                if isinstance(content, list):
                    texts = [c.get("text", "") for c in content if isinstance(c, dict)]
                    joined = " ".join(t for t in texts if t)
                    if joined:
                        return joined
    return str(input_data)


topic_guardrail_agent = Agent(
    name="Topic Guardrail Checker",
    instructions=(
        "Decide if the user's message should be allowed through to a farming "
        "assistant for Pakistani farmers. Say YES if the message is about "
        "farming, agriculture, crops, livestock, agri-business, or rural "
        "life in Pakistan. ALSO say YES for any of these, even though they "
        "aren't farming topics by themselves, because they are a normal part "
        "of a farmer starting or continuing a conversation with this "
        "assistant: \n"
        "- a greeting (e.g. 'hello', 'salaam', 'hi', 'assalam-o-alaikum')\n"
        "- the person introducing or giving their name (e.g. 'my name is "
        "ahmad', 'I am Ahmad', 'mera naam Ahmad hai')\n"
        "- the person giving farm details such as district/city, land size "
        "in acres, season (Rabi/Kharif), or water availability (e.g. "
        "'Multan, 5 acres, Rabi, low water')\n"
        "- a short one-word or one-phrase reply that looks like it's "
        "answering a question the assistant just asked (e.g. 'cotton', "
        "'low water', 'yes', 'no')\n"
        "Only say NO if the message is clearly unrelated to farming AND "
        "unrelated to any of the cases above — e.g. coding questions, "
        "general trivia, or requests with nothing to do with agriculture or "
        "the conversation itself. "
        "Respond with exactly one word: YES or NO, followed by a short reason."
    ),
    model=gemini_model,
    model_settings=GEMINI_SAFE_SETTINGS,
)


@input_guardrail
async def farming_topic_guardrail(
    ctx: RunContextWrapper, agent: Agent, input_text
) -> GuardrailFunctionOutput:
    """Rejects questions that are unrelated to farming (e.g. coding questions).

    When called from the web app, `input_text` may actually be the FULL
    structured conversation history (because a SQLiteSession is in use),
    which can include earlier tool calls like update_farmer_profile. We must
    strip that down to just the farmer's latest plain message before sending
    it to the topic-checker agent below, since that agent has no tools
    registered and would error out trying to resolve a tool call it doesn't
    know about.
    """
    latest_text = _extract_latest_user_text(input_text)
    result = await Runner.run(topic_guardrail_agent, latest_text, run_config=run_config)
    output_text = result.final_output or ""
    is_off_topic = output_text.strip().upper().startswith("NO")
    return GuardrailFunctionOutput(
        output_info=output_text,
        tripwire_triggered=is_off_topic,
    )


@output_guardrail
async def safety_output_guardrail(
    ctx: RunContextWrapper, agent: Agent, output_text: str
) -> GuardrailFunctionOutput:
    """Blocks responses containing exact pesticide dosages or human-medical advice."""
    lowered = output_text.lower()
    risky_markers = [
        "ml/liter", "ml per liter", "grams per liter", "mg/kg",
        "take this medicine", "human dosage", "for human consumption",
        "consult a doctor and take", "prescribe",
    ]
    tripped = any(marker in lowered for marker in risky_markers)
    return GuardrailFunctionOutput(
        output_info={"checked": True, "flagged_markers": [m for m in risky_markers if m in lowered]},
        tripwire_triggered=tripped,
    )


# ---------------------------------------------------------------------------
# 5. Specialist agents
# ---------------------------------------------------------------------------

LANGUAGE_INSTRUCTIONS = (
    "LANGUAGE RULE (follow strictly): Look ONLY at the farmer's most recent "
    "message to decide the reply language — ignore what language earlier "
    "messages in the conversation used. "
    "- If their most recent message is written in English (Latin script, "
    "English words/grammar), you MUST reply ENTIRELY in plain English. Do "
    "NOT mix in Roman Urdu or Urdu-script words. "
    "- If their most recent message is Roman Urdu (Urdu words spelled in "
    "Latin letters, e.g. 'aap kaisay hain'), reply entirely in Roman Urdu. "
    "- If their most recent message is Urdu script (اردو), reply entirely "
    "in Urdu script. "
    "Never default to Roman Urdu just because the topic is farming in "
    "Pakistan — the farmer's own most recent wording decides the language, "
    "every single time, even if earlier turns used a different language. "
    "Keep the tone warm, respectful, and simple — the user may have limited "
    "literacy or technical background."
)

agronomy_agent = Agent(
    name="Agronomy Agent",
    instructions=(
        "You are an expert agronomist helping Pakistani farmers with crop "
        "selection, fertilizer planning, and irrigation timing. Use the "
        "available tools to give concrete, practical answers. "
        + LANGUAGE_INSTRUCTIONS
    ),
    tools=[crop_advisor, fertilizer_calculator, irrigation_weather_advisor],
    model=gemini_model,
    model_settings=GEMINI_SAFE_SETTINGS,
    output_guardrails=[safety_output_guardrail],
)

pest_doctor_agent = Agent(
    name="Pest Doctor Agent",
    instructions=(
        "You are a crop health specialist helping diagnose pest and disease "
        "problems for Pakistani farmers. Use the pest_disease_doctor tool. "
        "NEVER give exact chemical dosages or human medical advice — always "
        "direct the farmer to a licensed agri-dealer or extension officer "
        "for exact application rates. " + LANGUAGE_INSTRUCTIONS
    ),
    tools=[pest_disease_doctor],
    model=gemini_model,
    model_settings=GEMINI_SAFE_SETTINGS,
    output_guardrails=[safety_output_guardrail],
)

market_agent = Agent(
    name="Market Agent",
    instructions=(
        "You help Pakistani farmers with mandi prices and government support "
        "schemes. Use the available tools. " + LANGUAGE_INSTRUCTIONS
    ),
    tools=[mandi_price_lookup, govt_support_finder],
    model=gemini_model,
    model_settings=GEMINI_SAFE_SETTINGS,
    output_guardrails=[safety_output_guardrail],
)

finance_agent = Agent(
    name="Finance Agent",
    instructions=(
        "You help Pakistani farmers estimate profitability for a crop cycle "
        "using the profit_estimator tool. If the farmer hasn't given enough "
        "numbers (area, yield, cost, price), ask for the missing ones. "
        + LANGUAGE_INSTRUCTIONS
    ),
    tools=[profit_estimator],
    model=gemini_model,
    model_settings=GEMINI_SAFE_SETTINGS,
    output_guardrails=[safety_output_guardrail],
)

ONBOARDING_INSTRUCTIONS = (
    "INTAKE RULE: Look at the ENTIRE conversation so far, including earlier "
    "messages — the farmer's name, district, land size, season, and water "
    "availability may have already been given in a previous message, even if "
    "it was several turns ago. Before asking anything, re-read the full "
    "history for these five things: name, district, land size (acres), "
    "season (Rabi/Kharif), water availability. "
    "As soon as ANY of these five appears anywhere in the conversation "
    "(current message or earlier), call the update_farmer_profile tool "
    "immediately with whatever you found, BEFORE writing your reply — do "
    "this even if it's only one detail. Never skip this step. "
    "If, after checking the full history and calling the tool for anything "
    "found, some of the five are still missing, reply with ONE single warm "
    "message asking ONLY for the still-missing ones — never re-ask for "
    "something already given anywhere earlier in the conversation. "
    "If all five are already known, do NOT ask anything — just answer the "
    "farmer's actual question, occasionally addressing them by name. "
    "If the farmer's question is urgent (e.g. a pest/disease emergency) or "
    "they explicitly decline to share details, go ahead and help anyway. "
    "LANGUAGE FOR THIS STEP: strictly follow the LANGUAGE RULE described "
    "separately — reply in English if their most recent message is English, "
    "Roman Urdu if Roman Urdu, Urdu script if Urdu script. Never default to "
    "Roman Urdu."
)

triage_agent = Agent(
    name="Triage Agent",
    instructions=(
        "You are Kisan Dost, a friendly assistant for Pakistani farmers. "
        + ONBOARDING_INSTRUCTIONS
        + " Whenever the farmer gives you their name, district, land size, "
        "season, or water availability — even one piece at a time — call the "
        "update_farmer_profile tool immediately to save it before doing "
        "anything else. Once intake is satisfied (or skipped per the rule "
        "above), read the farmer's question and hand off to the correct "
        "specialist: Agronomy Agent (crops, fertilizer, irrigation), Pest "
        "Doctor Agent (pests, diseases, plant symptoms), Market Agent (mandi "
        "prices, govt schemes), or Finance Agent (profit/cost estimates). If "
        "a question spans multiple areas, handle the primary intent first. "
        + LANGUAGE_INSTRUCTIONS
    ),
    tools=[update_farmer_profile, update_profile],
    handoffs=[agronomy_agent, pest_doctor_agent, market_agent, finance_agent],
    model=gemini_model,
    model_settings=GEMINI_SAFE_SETTINGS,
    input_guardrails=[farming_topic_guardrail],
)


# ---------------------------------------------------------------------------
# 6. Terminal loop
# ---------------------------------------------------------------------------

async def chat_once(user_input: str, previous_result=None, profile: "FarmerProfile" = None):
    """Run one turn of conversation. Returns the RunResult."""
    if previous_result is not None:
        input_data = previous_result.to_input_list() + [
            {"role": "user", "content": user_input}
        ]
    else:
        input_data = user_input

    try:
        result = await Runner.run(
            triage_agent, input_data, context=profile, run_config=run_config
        )
        return result, result.final_output
    except Exception as e:
        # Catches guardrail tripwire exceptions and any API errors gracefully.
        error_name = type(e).__name__
        if "GuardrailTripwireTriggered" in error_name or "InputGuardrail" in error_name:
            return previous_result, (
                "Maazrat! Main sirf zirat (farming) se mutaliq sawalat ka jawab "
                "de sakta hoon. Please ask a farming-related question."
            )
        if "OutputGuardrail" in error_name:
            return previous_result, (
                "I can't share exact chemical dosages or medical advice here — "
                "please consult a licensed agri-dealer or extension officer for "
                "the precise application rate."
            )
        return previous_result, f"[Error] Something went wrong: {e}"


async def main():
    print("=" * 60)
    print(" Kisan Dost — AI Agronomy Assistant (type 'exit' to quit)")
    print("=" * 60)

    result = None
    profile = FarmerProfile()
    while True:
        try:
            user_input = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nKhuda Hafiz!")
            break

        if user_input.lower() in {"exit", "quit"}:
            print("Khuda Hafiz!")
            break
        if not user_input:
            continue

        result, reply = await chat_once(user_input, result, profile)
        print(f"\nKisan Dost: {reply}")


if __name__ == "__main__":
    asyncio.run(main())
