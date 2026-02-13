# Creating MCP Servers for OpenFang

This guide walks you through building a new dual-interface MCP server for OpenFang. Every MCP server must support both calling patterns — LLM via MCP protocol and direct Python import — using the same underlying functions.

## Quick Start

```bash
# Copy the template
cp -r openfang/mcp_servers/_template openfang/mcp_servers/your_server_name

# Edit the files
# 1. server.py  — models, core functions, MCP registration
# 2. manifest.yaml — capability descriptions and metadata
# 3. tests/test_server.py — tests for both calling patterns
```

## Architecture

Every OpenFang MCP server follows the same three-layer pattern:

```
┌─────────────────────────────────────┐
│  MCP Tool Wrappers                  │  ← LLM calls these via MCP protocol
│  (string in, string out)            │
├─────────────────────────────────────┤
│  Core Functions                     │  ← Both callers use these
│  (typed Pydantic models in/out)     │
├─────────────────────────────────────┤
│  External API / Service             │  ← The actual work
└─────────────────────────────────────┘
```

**Core functions** are the real implementation. They accept Pydantic models, return Pydantic models, and are `async`.

**MCP tool wrappers** are thin adapters that convert string parameters to Pydantic models, call the core function, and serialize the result back to JSON. The LLM sees these as MCP tools.

**Python scripts** skip the MCP layer entirely and call core functions directly. Same logic, zero overhead.

## Step-by-Step Guide

### 1. Define Your Models

Start with Pydantic models for every request and response. These are the contract between callers and your server.

```python
from pydantic import BaseModel
from datetime import datetime

class GetWeatherRequest(BaseModel):
    """Request to get weather for a location."""
    city: str
    units: str = "celsius"  # "celsius" or "fahrenheit"

class WeatherResponse(BaseModel):
    """Weather data for a location."""
    city: str
    temperature: float
    conditions: str
    humidity: int
    retrieved_at: datetime
```

Rules:
- Every field must be typed
- Use `str | None = None` for optional fields
- Include a timestamp field on responses (`retrieved_at`, `sent_at`, etc.)
- Use descriptive docstrings — the LLM reads these

### 2. Implement Core Functions

Core functions are `async`, accept typed inputs, and return typed outputs. They should be importable and callable without any MCP infrastructure.

```python
async def get_weather(
    request: GetWeatherRequest,
    http_client: httpx.AsyncClient | None = None,
    api_key: str | None = None,
) -> WeatherResponse:
    """
    Get current weather for a city.

    Args:
        request: The weather request.
        http_client: Optional httpx client (for testing).
        api_key: Optional API key override (for testing).
    """
    key = api_key or _get_api_key()

    try:
        if http_client:
            response = await http_client.get(...)
        else:
            async with httpx.AsyncClient() as client:
                response = await client.get(...)

        data = response.json()
        return WeatherResponse(...)

    except httpx.HTTPError as e:
        logger.error(f"Weather API error: {e}")
        # Return a typed error response, don't raise
        return WeatherResponse(
            city=request.city,
            temperature=0.0,
            conditions="error",
            humidity=0,
            retrieved_at=datetime.now(timezone.utc),
        )
```

Key patterns:
- **Injectable dependencies**: Accept optional `http_client`, `db_path`, `api_key`, etc. for testability. Fall back to environment variables when not provided.
- **Error handling**: Catch external errors and return typed responses. Don't let `httpx.HTTPError` or `aiosqlite` exceptions propagate unhandled.
- **No global state**: Don't read config at module level. Use functions like `_get_api_key()` that read from `os.environ` at call time.

### 3. Register MCP Tools

MCP tool wrappers convert between string parameters (what the LLM sends) and your typed models.

```python
try:
    from mcp.server import Server

    server = Server("weather")

    @server.tool()
    async def mcp_get_weather(city: str, units: str = "celsius") -> str:
        """Get current weather for a city."""
        request = GetWeatherRequest(city=city, units=units)
        result = await get_weather(request)
        return result.model_dump_json()

except ImportError:
    server = None
```

Rules:
- Wrap in `try/except ImportError` so the server works without the `mcp` package
- MCP tool names should be prefixed with `mcp_` to distinguish from core functions
- Tool docstrings become the tool description the LLM sees — make them clear
- For complex inputs, accept JSON strings and parse them: `json.loads(data)`
- Always return `result.model_dump_json()`

### 4. Write the Manifest

The `manifest.yaml` describes your server's capabilities for the component registry.

```yaml
name: weather
version: 0.1.0
description: >
  Retrieves current weather data for cities worldwide
  using the OpenWeatherMap API.

capabilities:
  - id: get_weather
    description: "Get current weather conditions for a city"
    inputs:
      - name: city
        type: string
        required: true
      - name: units
        type: string
        default: "celsius"
    outputs:
      type: WeatherResponse
      fields: [city, temperature, conditions, humidity, retrieved_at]

requires:
  env_vars:
    - OPENWEATHER_API_KEY
  python_packages:
    - httpx>=0.27

tags: [weather, location, monitoring]
```

The `tags` field is used by the component registry for search and by the codification engine for discovery. Choose tags that describe the domain, not the implementation.

### 5. Write Tests

Tests must cover **both calling patterns**. Use mock HTTP transports for external API servers.

```python
import httpx
import pytest
from openfang.mcp_servers.weather.server import (
    GetWeatherRequest, WeatherResponse, get_weather,
)

def _mock_transport(response_data: dict) -> httpx.AsyncClient:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=response_data)
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


class TestDirectPythonCalls:
    """Test core functions via direct import (the pipeline pattern)."""

    async def test_get_weather(self) -> None:
        client = _mock_transport({"temp": 22.5, "conditions": "sunny", ...})
        result = await get_weather(
            GetWeatherRequest(city="London"),
            http_client=client,
            api_key="test-key",
        )
        assert isinstance(result, WeatherResponse)
        assert result.city == "London"

    async def test_network_error(self) -> None:
        async def failing(req):
            raise httpx.ConnectError("timeout")
        client = httpx.AsyncClient(transport=httpx.MockTransport(failing))

        result = await get_weather(
            GetWeatherRequest(city="London"),
            http_client=client,
            api_key="test-key",
        )
        assert result.conditions == "error"
```

For database-backed servers, use `tmp_path` fixtures:

```python
@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.db")

async def test_insert_and_query(db_path):
    await ensure_table(..., db_path=db_path)
    await insert(..., db_path=db_path)
    result = await query(..., db_path=db_path)
    assert result.count == 1
```

### 6. Validate Identifiers (Database Servers)

If your server constructs SQL queries, validate all identifiers to prevent injection:

```python
import re

_VALID_IDENTIFIER = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

def _validate_identifier(name: str) -> str:
    if not _VALID_IDENTIFIER.match(name):
        raise ValueError(f"Invalid SQL identifier: {name!r}")
    return name
```

Always use parameterized queries for values (`?` placeholders). Only use validated identifiers for table and column names.

## Directory Structure

```
openfang/mcp_servers/your_server/
├── __init__.py          # Module docstring
├── server.py            # Models + core functions + MCP registration
├── manifest.yaml        # Component manifest
└── tests/
    ├── __init__.py
    └── test_server.py   # Tests for both calling patterns
```

## Checklist

Before submitting a new MCP server:

- [ ] All request/response types are Pydantic models
- [ ] Core functions are `async` and accept typed inputs
- [ ] Core functions accept injectable dependencies (`http_client`, `db_path`, etc.)
- [ ] Error handling catches external failures and returns typed responses
- [ ] MCP tool wrappers are registered in a `try/except ImportError` block
- [ ] `manifest.yaml` describes all capabilities with input/output schemas
- [ ] Tests cover the direct Python calling pattern
- [ ] Tests use mock transports (no real API calls in CI)
- [ ] SQL identifiers are validated if the server touches a database
- [ ] `__init__.py` has a descriptive module docstring
- [ ] No secrets or API keys are hardcoded — all come from environment variables

## Reference Implementations

Study these existing servers for patterns:

| Server | Pattern | Key Technique |
|--------|---------|---------------|
| `database` | SQLite CRUD | Injectable `db_path`, identifier validation |
| `slack_notify` | HTTP API | Injectable `http_client`, error recovery |
| `brave_search` | HTTP API | Injectable `http_client` + `api_key` |
