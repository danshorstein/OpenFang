# OpenFang

### *Let the snake do the work.*

**OpenFang** is an open-source fork of [OpenClaw](https://github.com/openclaw/openclaw) that radically rethinks how personal AI agents should operate. Instead of routing every task through an LLM — burning tokens, adding latency, and introducing hallucination risk — OpenFang treats the LLM as a **strategist and engineer** that writes, deploys, and maintains deterministic Python automations.

The LLM builds the factory. Python runs the factory. The LLM steps back in only when something breaks or something new is needed.

> **OpenClaw:** "Let me think about how to check your email… okay, I'll call the Gmail API… let me parse this response… here's what I found."
>
> **OpenFang:** The Python cron job already checked your email 30 seconds ago. The data is in your database. The LLM just formats a response from cached results — or you glance at the dashboard and skip the LLM entirely.

**Result:** 90%+ reduction in token costs, faster execution, more reliable automations, and a system that gets *cheaper* over time as more workflows graduate from LLM-orchestrated to Python-automated.

-----

## Table of Contents

1. [Philosophy](#philosophy)
1. [The Org Chart Model](#the-org-chart-model)
1. [Architecture Overview](#architecture-overview)
1. [The Dual-Caller MCP Pattern](#the-dual-caller-mcp-pattern)
1. [The Workflow Lifecycle](#the-workflow-lifecycle)
1. [System Components](#system-components)
1. [Interaction Model](#interaction-model)
1. [Project Structure](#project-structure)
1. [Getting Started](#getting-started)
1. [Contributing](#contributing)
1. [License](#license)

-----

## Philosophy

OpenFang is built on a single principle: **LLMs should write automations, not be automations.**

The current generation of AI agent frameworks treat the LLM as a universal worker. Every task, no matter how routine or deterministic, passes through the language model. This is like hiring a brilliant consultant to manually sort your mail every morning. They *can* do it, but it's a spectacular waste of their talents and your money.

OpenFang inverts this. The LLM is the **architect and supervisor**. It designs systems, writes code, documents components, and reviews operations. The actual work — the API calls, data transforms, scheduled jobs, notifications, and pipelines — is executed by deterministic Python scripts that the LLM wrote and deployed.

### Core Beliefs

1. **Tokens are expensive. CPU cycles are cheap.** Every task that *can* be deterministic *should* be deterministic.
2. **LLMs should be used for what they're uniquely good at.** Creativity. Reasoning. Synthesis. Natural language understanding. Judgment calls.
3. **Automations should be born in conversation and graduate to code.** The LLM figures out how to meet a need, codifies it into Python, deploys it, and steps back.
4. **Every component should be reusable.** The LLM invests tokens once to build and document a component well. That investment pays dividends forever.
5. **The system should get cheaper over time, not more expensive.** A mature OpenFang instance should cost a fraction of what it cost in its first week.

-----

## The Org Chart Model

OpenFang uses a tiered intelligence model that mirrors how well-run organizations allocate talent.

### C-Suite — Opus (frontier model)

- Called rarely — once daily for strategic review, plus on-demand for novel problems.
- Designs workflow architectures, makes high-level decisions, performs business synthesis, handles escalations.

### Middle Management — Sonnet/Haiku (capable model)

- Called moderately — handles user chat, interprets requests, triages errors.
- Generates responses from cached data, writes straightforward automations, triages pipeline failures.

### The Workforce — Python

- Runs constantly — 24/7 on cron schedules and event triggers.
- API calls, data collection, transforms, storage, pipeline orchestration, health checks, notifications.
- Near-zero marginal cost. Millisecond execution. No tokens consumed.

### Escalation Protocol

```
Python job fails
    → Logs error, flags for review
        → Sonnet picks it up at next review cycle
            → Sonnet fixes it? Done. Deploys patch.
            → Sonnet can't fix it? Escalates to Opus with summary.
                → Opus redesigns the approach
                    → Hands back down to Python layer
```

-----

## The Dual-Caller MCP Pattern

Every OpenFang MCP server is a standard MCP server that *also* exposes a Python-importable interface. The LLM interacts with it via MCP protocol. Python scripts call the same underlying functions directly.

```python
# Both callers use the same underlying functions:

# Python orchestration (no LLM, no tokens)
from openfang.mcp_servers.youtube_analytics.server import get_channel_stats
stats = await get_channel_stats(request)  # Direct call. Milliseconds. Zero tokens.

# LLM via MCP protocol
# Tool: mcp_get_channel_stats → same function executes underneath
```

-----

## Project Structure

```
openfang/
├── README.md
├── pyproject.toml
│
├── gateway/                            # Forked from OpenClaw (existing Node.js)
│
├── openfang/                           # Python core
│   ├── mcp_servers/                    # Dual-interface MCP servers
│   │   ├── _template/                  # Template for new MCP servers
│   │   ├── database/
│   │   ├── slack_notify/
│   │   ├── brave_search/
│   │   └── ...
│   │
│   ├── orchestration/                  # Python automation engine
│   │   ├── executor.py                 # Pipeline runner
│   │   ├── scheduler.py                # Cron management
│   │   ├── log_aggregator.py           # Structured logging
│   │   └── sandbox.py                  # Isolated test runner
│   │
│   ├── intelligence/                   # LLM integration layer
│   │   ├── router.py                   # Request classification + routing
│   │   ├── codifier.py                 # Workflow → Python script generator
│   │   ├── supervisor.py               # Periodic log review + patching
│   │   ├── escalation.py               # Tier escalation logic
│   │   └── models.py                   # LLM client config
│   │
│   ├── registry/                       # Automation + component tracking
│   │   ├── automation_registry.py      # SQLite-backed automation store
│   │   ├── component_registry.py       # MCP server capability index
│   │   └── schema.sql                  # Database schema
│   │
│   └── pipelines/                      # Deployed automation scripts
│
├── dashboard/                          # Web frontend
│   ├── backend/                        # FastAPI application
│   └── frontend/                       # React/HTMX frontend
│
├── config/                             # Configuration
│   ├── openfang.yaml
│   ├── llm_tiers.yaml
│   └── schedules.yaml
│
└── tests/                              # Python tests
```

-----

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 22+ (for OpenClaw gateway)
- pnpm (for Node.js dependencies)

### Installation

```bash
# Clone the repository
git clone https://github.com/openfang/openfang.git
cd openfang

# Install Python dependencies
pip install -e ".[dev]"

# Install Node.js dependencies (for gateway)
cd gateway && pnpm install && cd ..

# Run tests
pytest tests/

# Start the full stack
docker-compose up
```

-----

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

Key rules:
1. Every MCP server must support both calling patterns (MCP protocol + direct Python import).
2. Every MCP server must include a `manifest.yaml`.
3. All Python code must be typed (Pydantic models for I/O, type hints throughout).
4. All pipelines must include comprehensive docstrings.
5. Tests must cover both the MCP calling pattern and the direct Python calling pattern.

-----

## License

MIT License — see [LICENSE](LICENSE) for details.

-----

## Acknowledgments

OpenFang is a fork of [OpenClaw](https://github.com/openclaw/openclaw). We respect the work that went into OpenClaw and the community it has built. OpenFang represents a different philosophy about how AI agents should operate — prioritizing efficiency and determinism while preserving the conversational interface that makes AI agents accessible.

-----

*OpenFang — Bite once, automate forever.*
