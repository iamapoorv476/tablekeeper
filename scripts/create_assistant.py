"""
Creates the four function tools on Vapi, then creates the assistant
referencing them by ID (current Vapi API requires tools to be created
separately and attached via model.toolIds — embedding them inline under
assistant.tools or model.tools is rejected with a 400).

Usage:
    export VAPI_API_KEY="your-vapi-private-key"
    export SERVER_URL="https://your-tunnel-or-railway-url/vapi/tools"
    python scripts/create_assistant.py
"""
import os
import sys
from datetime import datetime
import requests

VAPI_API_KEY = os.environ.get("VAPI_API_KEY")
SERVER_URL = os.environ.get("SERVER_URL")

LANGUAGE = os.environ.get("LANGUAGE", "en")
VOICE_PROVIDER = os.environ.get("VOICE_PROVIDER", "azure" if LANGUAGE == "sv" else "deepgram")
VOICE_ID = os.environ.get("VOICE_ID", "sv-SE-SofieNeural" if LANGUAGE == "sv" else "luna")
TRANSCRIBER_LANGUAGE = os.environ.get("TRANSCRIBER_LANGUAGE", "sv" if LANGUAGE == "sv" else "en-US")

if LANGUAGE == "sv" and not VOICE_ID:
    sys.exit(
        "LANGUAGE=sv requires VOICE_ID to be set explicitly.\n"
        "Go to Vapi's dashboard, open the voice picker, search for a Swedish "
        "voice, and set VOICE_PROVIDER + VOICE_ID to what you find — I don't "
        "have a verified default for this, see the comment above LANGUAGE."
    )

if not VAPI_API_KEY:
    sys.exit("Set VAPI_API_KEY first: export VAPI_API_KEY=your-vapi-private-key")
if not SERVER_URL:
    sys.exit("Set SERVER_URL first: export SERVER_URL=https://your-tunnel-or-railway-url/vapi/tools")

HEADERS = {
    "Authorization": f"Bearer {VAPI_API_KEY}",
    "Content-Type": "application/json",
}

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "check_availability",
            "description": "Check whether a table is free for a given party size, date, and time. Always call this before create_reservation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "party_size": {"type": "integer", "description": "Number of guests"},
                    "date": {"type": "string", "description": "Date in YYYY-MM-DD format"},
                    "time": {"type": "string", "description": "Time in 24-hour HH:MM format"},
                },
                "required": ["party_size", "date", "time"],
            },
        },
        "server": {"url": SERVER_URL},
    },
    {
        "type": "function",
        "function": {
            "name": "create_reservation",
            "description": "Book a table. Only call this after check_availability has confirmed the slot is available.",
            "parameters": {
                "type": "object",
                "properties": {
                    "party_size": {"type": "integer"},
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                    "time": {"type": "string", "description": "24-hour HH:MM"},
                    "guest_name": {"type": "string"},
                },
                "required": ["party_size", "date", "time", "guest_name"],
            },
        },
        "server": {"url": SERVER_URL},
    },
    {
        "type": "function",
        "function": {
            "name": "modify_reservation",
            "description": "Change the time, date, or party size of the caller's existing reservation. Resolves the reservation automatically from the caller's phone number if reservation_id isn't known.",
            "parameters": {
                "type": "object",
                "properties": {
                    "new_date": {"type": "string", "description": "YYYY-MM-DD, only if the date is changing"},
                    "new_time": {"type": "string", "description": "24-hour HH:MM, only if the time is changing"},
                    "new_party_size": {"type": "integer", "description": "Only if the party size is changing"},
                },
            },
        },
        "server": {"url": SERVER_URL},
    },
        {
        "type": "function",
        "function": {
            "name": "request_callback",
            "description": (
                "Log a callback request when you cannot finish something on this call: a tool "
                "failed twice, the request is outside what you can do (private events, parties "
                "over 8, complaints, anything not in the menu/policy info you were given), or "
                "the guest asks for a human. Never end a call leaving the guest without a path."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "Short reason you could not close it, e.g. 'party of 22, private event' or 'modify_reservation could not find the booking'",
                    },
                    "context": {
                        "type": "string",
                        "description": "What the guest actually wants, in enough detail that a human can pick it up cold without relistening to the call",
                    },
                    "guest_name": {"type": "string", "description": "Name if the guest gave one"},
                },
                "required": ["reason", "context"],
            },
        },
        "server": {"url": SERVER_URL},
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_guest",
            "description": "Look up whether the caller is a returning guest. Call this once, silently, at the very start of the call.",
            "parameters": {"type": "object", "properties": {}},
        },
        "server": {"url": SERVER_URL},
    },
]

SYSTEM_PROMPT_TEMPLATE = """You are Mia, the phone host at Basilico Trattoria, an Italian restaurant. You are warm, brief, and efficient — this is a phone call, not a chat, so keep every response to 1-2 short sentences unless reading back a confirmation.

TODAY'S DATE: {{"now" | date: "%A, %B %d, %Y", "Asia/Kolkata"}}. This is filled in by Vapi fresh on every single call — never assume it was set once and is now stale. When the caller says "today", "tomorrow", "next Friday", or any other relative date, compute the actual calendar date yourself using today's date above before calling any tool. Always pass tool arguments as an exact YYYY-MM-DD date — never pass the word "tomorrow" itself to a tool.

YOUR JOB:
1. At the very start of the call, silently call lookup_guest with the caller's number. If known, greet them by name and naturally reference their preference once (e.g. 'Hi Aarav, welcome back — window seat again tonight?'). If unknown, just greet normally.
2. If they want to book a table: collect party size, date, time, and name (skip name if lookup_guest already gave you one). Before confirming ANYTHING, call check_availability. If available, call create_reservation and read back the confirmation_summary exactly as returned. If NOT available, offer the alternatives returned by the tool — never invent times yourself.
3. If they want to change an existing booking: call modify_reservation with whatever they're changing (time/date/party size). If it fails, offer the alternatives it returns.
4. If they ask about the menu, dietary options, or restaurant policies, answer using ONLY this information:

MENU: Our signature dish is the truffle tagliatelle. Popular starters include burrata with heirloom tomatoes and wood-fired focaccia.

DIETARY: We have a full vegan menu including vegan lasagna and mushroom risotto. Gluten-free pasta is available as a substitute on any pasta dish at no extra charge, plus gluten-free bread.

POLICIES: Reservations are held 15 minutes past the booked time before the table may be released. Parties larger than 8 require a deposit and 24 hours notice. Dress code is smart casual, nothing strict.

NEVER LEAVE A GUEST STRANDED:
Every call must end with the guest having a path forward. If you cannot finish something —
a tool failed twice, they want a private event or a party over 8, they have a complaint, they
ask for a human, or they ask anything you were not given the information to answer — do NOT
apologise vaguely and stop. Call request_callback with what they wanted, tell them the team
has it and will call back, and confirm the number to reach them on. A logged callback is a
good outcome. A guest hanging up with nothing is not.

RULES:
- Never make up availability, table numbers, or policies not listed above.
- Never call create_reservation without calling check_availability first in the same turn sequence.
- Keep responses short — you're on a phone call, not writing an email.
- If party size, date, time, or name is missing, ask for just the missing piece, not everything at once.
- Confirm bookings by reading back the exact confirmation_summary text from the tool result, not your own paraphrase.
- CRITICAL: every tool result is a JSON object with a "success" field. If a tool returns "success": false (or an "error" field), the action did NOT happen — the reservation was NOT created or changed, regardless of anything else in the response. You must NEVER tell the caller something succeeded, was "updated", "confirmed", or "booked" unless the tool's own response says "success": true. If a tool fails, say plainly that it didn't work, tell them the specific error if one was given, and either try again with corrected information or ask them to call back — never paper over a failure with a reassuring guess.
- When a tool result includes a "next_step" field, follow it. It tells you exactly how to recover
  from that specific failure. Do not improvise a different recovery."""

LANGUAGE_CONTENT = {
    "en": {
        "first_message": "Thanks for calling Basilico Trattoria, this is Mia — how can I help you today?",
        "menu": "Our signature dish is the truffle tagliatelle. Popular starters include burrata with heirloom tomatoes and wood-fired focaccia.",
        "dietary": "We have a full vegan menu including vegan lasagna and mushroom risotto. Gluten-free pasta is available as a substitute on any pasta dish at no extra charge, plus gluten-free bread.",
        "policies": "Reservations are held 15 minutes past the booked time before the table may be released. Parties larger than 8 require a deposit and 24 hours notice. Dress code is smart casual, nothing strict.",
        "language_instruction": "",
    },
    "sv": {
        "first_message": "Tack för att du ringer Basilico Trattoria, det här är Mia — hur kan jag hjälpa dig idag?",
        "menu": "Vår signaturrätt är tryffeltagliatelle. Populära förrätter är burrata med arvsorterade tomater och vedeldad focaccia.",
        "dietary": "Vi har en komplett vegansk meny, inklusive vegansk lasagne och svamprisotto. Glutenfri pasta finns som ersättning till alla pastarätter utan extra kostnad, samt glutenfritt bröd.",
        "policies": "Bordsbokningar hålls i 15 minuter efter den bokade tiden innan bordet kan släppas. Sällskap större än 8 personer kräver en deposition och 24 timmars varsel. Klädkoden är smart casual, inget strikt.",
        "language_instruction": "\n\nIMPORTANT: Always speak to the caller in Swedish, regardless of what language they use. Every spoken response must be in Swedish. This instruction overrides nothing else — check_availability, create_reservation, etc. still take the same English field names and English-formatted dates/times as arguments; only what you SAY to the caller is in Swedish.",
    },
}

_content = LANGUAGE_CONTENT[LANGUAGE]

SYSTEM_PROMPT = (
    SYSTEM_PROMPT_TEMPLATE
    .replace(
        "MENU: Our signature dish is the truffle tagliatelle. Popular starters include burrata with heirloom tomatoes and wood-fired focaccia.",
        f"MENU: {_content['menu']}",
    )
    .replace(
        "DIETARY: We have a full vegan menu including vegan lasagna and mushroom risotto. Gluten-free pasta is available as a substitute on any pasta dish at no extra charge, plus gluten-free bread.",
        f"DIETARY: {_content['dietary']}",
    )
    .replace(
        "POLICIES: Reservations are held 15 minutes past the booked time before the table may be released. Parties larger than 8 require a deposit and 24 hours notice. Dress code is smart casual, nothing strict.",
        f"POLICIES: {_content['policies']}",
    )
    #.format(today=datetime.now().strftime("%A, %B %d, %Y"))
    + _content["language_instruction"]
)

def create_tool(tool_def):
    resp = requests.post("https://api.vapi.ai/tool", headers=HEADERS, json=tool_def)
    if resp.status_code >= 300:
        print(f"Failed to create tool '{tool_def['function']['name']}' ({resp.status_code}):")
        print(resp.text)
        sys.exit(1)
    data = resp.json()
    print(f"  Created tool: {tool_def['function']['name']} -> {data['id']}")
    return data["id"]


def create_assistant(tool_ids):
    name_suffix = " (Swedish)" if LANGUAGE == "sv" else ""
    payload = {
       "name": f"Basilico Trattoria Host{name_suffix}",
       "firstMessage": _content["first_message"],
        "model": {
            "provider": "anthropic",
            "model": "claude-haiku-4-5-20251001",
            "temperature": 0.4,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}],
            "toolIds": tool_ids,
        },
        "voice": {"provider": VOICE_PROVIDER, "voiceId": VOICE_ID},
        "transcriber": {"provider": "deepgram", "model": "nova-2", "language": TRANSCRIBER_LANGUAGE},
        "server": {"url": SERVER_URL},
        "endCallFunctionEnabled": True,
        "maxDurationSeconds": 300,
    }
    resp = requests.post("https://api.vapi.ai/assistant", headers=HEADERS, json=payload)
    if resp.status_code >= 300:
        print(f"Failed to create assistant ({resp.status_code}):")
        print(resp.text)
        sys.exit(1)
    return resp.json()


print("Creating tools...")
tool_ids = [create_tool(t) for t in TOOL_DEFINITIONS]

print("\nCreating assistant...")
assistant = create_assistant(tool_ids)

print(f"\nAssistant created: {assistant['id']}")
print(f"Name: {assistant['name']}")
print("\nNext step: go to Vapi dashboard -> Phone Numbers -> your number")
print(f"-> assign this assistant ({assistant['id']}) to it.")