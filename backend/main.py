"""
Vasaloppet Q&A Backend

Orchestrates between the frontend, Claude API, and the isolated code executor.
Maintains per-session conversation history for multi-turn interactions.
"""

import os
import re
import time
import uuid

import anthropic
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Work around SSL certificate verification issues in Docker
# (e.g. corporate proxies injecting self-signed certs)
import ssl

_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE

app = FastAPI(title="Vasaloppet Q&A Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
EXECUTOR_URL = os.environ.get("EXECUTOR_URL", "http://executor:9000")
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
MAX_RETRIES = 2
SESSION_TTL = 1800  # 30 minutes

# ---------------------------------------------------------------------------
# Session store: session_id -> { "messages": [...], "last_active": timestamp }
# ---------------------------------------------------------------------------
sessions: dict[str, dict] = {}

SYSTEM_PROMPT = """\
You are a data analyst assistant specializing in Vasaloppet cross-country ski race data.
You have access to a pandas DataFrame `df` with {row_count} rows of historical results from 1922 to 2026.

## About Vasaloppet

Vasaloppet is the world's oldest and largest cross-country ski race, held annually in
Dalarna, Sweden. The race covers 90 km from Sälen to Mora, retracing the route that
King Gustav Vasa is said to have skied in 1520 when fleeing Danish soldiers. Two men
from Mora caught up with him and convinced him to return and lead a rebellion, which
ultimately led to Swedish independence and Gustav Vasa becoming King of Sweden.

The first race was held on 19 March 1922 and has been held every year since (except
1932 and 1934 due to lack of snow, and 1990 due to warm weather). The race takes
place on the first Sunday of March. The main event is the classic-style 90 km race,
but Vasaloppet Week also includes shorter races and a 90 km skating-style race
(Vasaloppet Öppet Spår).

Key checkpoints along the route (with approximate distances from start):
- Smågan (~24 km) — first major feed station
- Mångsbodarna (~35 km)
- Risberg (~47 km) — roughly halfway
- Evertsberg (~58 km) — the famous Evertsberg climb
- Oxberg (~71 km)
- Hökberg (~81 km)
- Eldris (~88 km) — final checkpoint before the finish
- Mora (~90 km) — the finish line, where the winner touches the finish post

The race motto is "I fäders spår — för framtids segrar" (In the footsteps of our
forefathers — for future victories). The winner's wreath is a crown of laurel, and
the last finisher to cross the line before the cutoff is called "Siste Smansen."

Finishers can earn a Vasaloppet medal based on their time relative to the winner's
time. To receive a medal, a skier must finish within 1.5 times the winner's finish
time. This makes the medal cutoff different each year depending on conditions and
the winning pace.

Along the course through the forests of Dalarna, skiers may occasionally spot
järv (wolverine, Gulo gulo) — one of Sweden's rarest and most elusive predators.
The Swedish woods are home to a notable population of järvar, and sightings near
the Vasaloppet trail, while uncommon, are part of the wilderness character of the race.

## DataFrame schema

Columns and dtypes:
- Year (int64): Race year, 1922-2026
- Name (str): Participant name, format "Lastname, Firstname"
- Nation (str): 3-letter country code (SWE, NOR, FIN, DEN, GER, CZE, ITA, SUI, EST, AUT, and ~90 more)
- Status (str): "Finished", "Did Not Finish", "Not Started", "Started", or NaN
- Sex (str): "M" or "W"
- Bib (str): Bib number (e.g. "M10997"), may be NaN for older years
- StartGroup (str): Start group number as string ("1" through "10"), NaN for older years
- Group (str): Age/sex category (e.g. "H21", "H35", "H40", "H45", "H50", "H55", "H60", "H65", "D21", "D35", "D40", "D45", "D50", "D55", "D60"). H=Herrar(Men), D=Damer(Women). Number is minimum age.
- Checkpoint split times in SECONDS (float64), NaN if participant didn't reach that checkpoint:
  - Hogsta_punkten: ~11 km
  - Smagan: ~24 km
  - Mangsbodarna: ~35 km
  - Risberg: ~47 km
  - Evertsberg: ~58 km
  - Oxberg: ~71 km
  - Hokberg: ~81 km
  - Eldris: ~88 km
  - Finish: ~90 km (total race distance)

Note: The actual column names use Swedish characters: "Högsta punkten", "Smågan", "Mångsbodarna", etc.

Additionally, timedelta versions of each split column are available with a `_td` suffix:
- "Högsta punkten_td", "Smågan_td", ..., "Finish_td" (pandas Timedelta type)

SPLIT_COLS is available as a list: ["Högsta punkten", "Smågan", "Mångsbodarna", "Risberg", "Evertsberg", "Oxberg", "Hökberg", "Eldris", "Finish"]

## Available packages in the executor
- pandas (as pd)
- numpy (as np)
- matplotlib.pyplot (as plt)
- seaborn (as sns)
- scipy

## Instructions

When the user asks a question about the data:

1. **ALWAYS write Python code to answer questions about actual data values** (e.g. who won, how many participants, what was someone's time, rankings, statistics, etc.). NEVER answer data questions from memory or training knowledge — your training data may be inaccurate or outdated. The only source of truth is the DataFrame `df`.

2. You may answer in plain text WITHOUT code ONLY for:
   - Meta-questions about the schema (e.g. "what columns are available?", "what format are the times in?")
   - General knowledge questions about Vasaloppet (e.g. history, route, traditions, rules) using the information provided above.
   NEVER answer in plain text when the question involves specific data values, results, or statistics.

3. Write Python code in a fenced code block tagged ```python.
   - The DataFrame `df` is already loaded and available.
   - Use `print()` to output text results.
   - Use matplotlib/seaborn to create figures. Do NOT call `plt.savefig()` or `plt.show()` — the system captures figures automatically.
   - Format times nicely for the user: convert seconds to HH:MM:SS when displaying.
   - Always include clear axis labels and titles on charts.
   - Be thorough but concise in printed output.

4. IMPORTANT: Only write ONE code block per response. Do not mix code and text explanations before the code. Put your explanation AFTER the code block, or include it as print() statements within the code.

5. If your code produces an error, you'll be told the traceback. Fix the code and try again.

6. When working with times, remember they are in seconds. To convert to a readable format:
   `pd.to_timedelta(seconds, unit='s')` or manual formatting.

7. NEVER guess or fabricate data values. If the data doesn't contain what was asked, say so based on the code output.
"""


def cleanup_sessions():
    """Remove sessions older than SESSION_TTL."""
    now = time.time()
    expired = [
        sid for sid, s in sessions.items() if now - s["last_active"] > SESSION_TTL
    ]
    for sid in expired:
        del sessions[sid]


def get_or_create_session(session_id: str | None) -> tuple[str, list]:
    """Return (session_id, messages) for the given or a new session."""
    cleanup_sessions()
    if session_id and session_id in sessions:
        sessions[session_id]["last_active"] = time.time()
        return session_id, sessions[session_id]["messages"]
    sid = session_id or str(uuid.uuid4())
    sessions[sid] = {"messages": [], "last_active": time.time()}
    return sid, sessions[sid]["messages"]


def extract_code_block(text: str) -> str | None:
    """Extract Python code from a fenced code block in the response."""
    pattern = r"```python\s*\n(.*?)```"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None


async def execute_code(code: str) -> dict:
    """Send code to the executor container and return the result."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(f"{EXECUTOR_URL}/execute", json={"code": code})
        resp.raise_for_status()
        return resp.json()


class AskRequest(BaseModel):
    question: str
    session_id: str | None = None


class AskResponse(BaseModel):
    text: str
    image: str | None = None
    session_id: str


@app.get("/health")
@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/ask", response_model=AskResponse)
async def ask(req: AskRequest):
    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured")

    session_id, messages = get_or_create_session(req.session_id)

    # Add the user's question
    messages.append({"role": "user", "content": req.question})

    http_client = httpx.Client(verify=_ssl_ctx)
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, http_client=http_client)

    # Retry loop: ask Claude, execute code if needed, retry on errors
    final_text = ""
    final_image = None

    for attempt in range(MAX_RETRIES + 1):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=4096,
                system=SYSTEM_PROMPT.format(row_count="764,830"),
                messages=messages,
            )
        except anthropic.APIError as e:
            raise HTTPException(
                status_code=502, detail=f"Anthropic API error: {e.message}"
            )

        assistant_text = response.content[0].text
        code = extract_code_block(assistant_text)

        if code is None:
            # Claude answered directly without code
            messages.append({"role": "assistant", "content": assistant_text})
            final_text = assistant_text
            break

        # Execute the code
        try:
            result = await execute_code(code)
        except Exception as e:
            messages.append({"role": "assistant", "content": assistant_text})
            error_msg = f"Failed to reach the code executor: {e}"
            messages.append(
                {
                    "role": "user",
                    "content": f"Error executing code:\n{error_msg}\nPlease fix the code.",
                }
            )
            final_text = f"Execution error: {error_msg}"
            continue

        if result.get("error"):
            # Code errored — feed traceback back to Claude
            messages.append({"role": "assistant", "content": assistant_text})
            error_feedback = (
                f"The code produced an error:\n```\n{result['error']}\n```\n"
                "Please fix the code and try again."
            )
            messages.append({"role": "user", "content": error_feedback})
            final_text = f"Code error (attempt {attempt + 1}): {result['error']}"
            continue

        # Success
        messages.append({"role": "assistant", "content": assistant_text})

        stdout = result.get("stdout", "").strip()
        image = result.get("image")

        # Build a clean text response from the code execution output only.
        # We discard Claude's surrounding text because it may contain
        # hallucinated answers not grounded in the actual data.
        if stdout:
            final_text = stdout
        else:
            final_text = "Done."
        final_image = f"data:image/png;base64,{image}" if image else None

        # Add a summary of the execution result to the conversation so Claude
        # knows what happened for follow-up questions
        exec_summary = ""
        if stdout:
            exec_summary += f"Code output:\n{stdout}\n"
        if image:
            exec_summary += "[A figure was generated and displayed to the user.]\n"
        if exec_summary:
            messages.append(
                {
                    "role": "user",
                    "content": f"[System: the code executed successfully.]\n{exec_summary}",
                }
            )
            messages.append(
                {
                    "role": "assistant",
                    "content": "Understood, the results have been shown to the user.",
                }
            )

        break

    return AskResponse(text=final_text, image=final_image, session_id=session_id)
