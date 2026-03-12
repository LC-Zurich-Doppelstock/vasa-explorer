# Vasaloppet Data Explorer

AI-powered chat interface for querying 764,830 Vasaloppet cross-country ski race results (1922–2026). Ask questions in natural language, get answers grounded in real data — as text, tables, or matplotlib charts.

## Architecture

Three Docker containers with network isolation:

```
┌─────────┐       ┌─────────┐       ┌──────────┐
│Frontend │──────▶│ Backend │──────▶│ Executor │
│ (nginx) │  HTTP │(FastAPI)│  MCP  │(FastMCP) │
└─────────┘       └─────────┘       └──────────┘
  :8088          frontend-net      backend-net
                 + backend-net      (internal)
```

- **Frontend** — Vanilla HTML/CSS/JS served by nginx. Markdown rendering via marked.js. No framework.
- **Backend** — FastAPI app acting as MCP client. Orchestrates: receives user question → calls LLM → extracts generated Python code → sends to executor → returns results. Manages conversation sessions and retry logic (including auto-installing missing pip packages).
- **Executor** — MCP server (Streamable HTTP transport) that runs LLM-generated Python code in a `ProcessPoolExecutor` sandbox against the dataset. Exposes tools (`execute_python`, `install_package`) and resources (`data-dictionary`, `installed-packages`) via MCP.

The executor sits on an internal-only Docker network — not reachable from outside.

## How it works

1. User asks a natural language question
2. Backend sends the question + conversation history + system prompt (with data dictionary and package list from MCP resources) to the LLM
3. LLM generates pandas/matplotlib code
4. Backend extracts the code and calls the executor's `execute_python` MCP tool
5. Executor runs the code in an isolated worker process (30s timeout), captures stdout and any matplotlib figures
6. Results (text + optional PNG chart) are returned to the user
7. On errors, the LLM gets the traceback and retries (up to 2 retries). Import errors trigger automatic `pip install` via the `install_package` tool before retrying.

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | Vanilla JS, nginx, marked.js |
| Backend | Python, FastAPI, MCP SDK (client) |
| Executor | Python, MCP SDK (server/FastMCP), pandas, matplotlib, seaborn, scipy |
| LLM providers | Anthropic (Claude), OpenAI (GPT) — via raw httpx, no SDKs |
| Transport | MCP Streamable HTTP between backend ↔ executor |
| Infrastructure | Docker Compose, isolated networks |

## Dataset

`results_clean.csv` — 764,830 rows, 17 columns. Every Vasaloppet result from 1922 to 2026 (102 race years — 1932, 1934, 1990 were cancelled). Includes finish times, checkpoint splits (from 2001), nations, age groups, and status.

## Running

```bash
cp .env.example .env  # add your ANTHROPIC_API_KEY and/or OPENAI_API_KEY
docker compose up --build
```

Open `http://localhost:8088`.

API keys can also be entered per-session in the browser's settings modal.

## Key design decisions

- **MCP as the executor protocol** — The executor exposes tools and resources via the Model Context Protocol rather than a custom REST API. This was a deliberate learning exercise. Resources provide the LLM with a live data dictionary and package list; tools handle code execution and package installation.
- **No LLM SDK dependencies** — Provider integrations (`providers.py`) use raw `httpx` calls. Avoids heavyweight SDKs and version coupling.
- **Process pool sandbox** — Code runs in forked worker processes with `ProcessPoolExecutor`. Each worker loads its own dataset copy. stdout and matplotlib state are process-local, so executions are fully parallel with no locking.
- **Network isolation** — The executor (which runs arbitrary code) is on an internal Docker network, unreachable from the frontend or internet.
- **Dark-themed charts** — Matplotlib/seaborn use a custom dark theme matching the UI. Applied in both main and worker processes.
- **Auto-install on ImportError** — When code fails with a missing module, the backend calls `install_package`, then retries the same code. Ephemeral (lost on container restart).
- **Grounded answers** — The frontend displays raw code output, not the LLM's surrounding text. This prevents hallucinated answers that aren't backed by the actual data.
