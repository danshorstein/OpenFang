-- OpenFang Registry Schema
-- SQLite database for tracking automations, logs, and components.

CREATE TABLE IF NOT EXISTS automations (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    description     TEXT,
    pipeline_file   TEXT NOT NULL,
    cron_schedule   TEXT,
    mcp_servers     TEXT,                -- JSON array of MCP server IDs used
    status          TEXT DEFAULT 'active', -- active | paused | error | deprecated
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_by      TEXT,                -- 'llm:opus' | 'llm:sonnet' | 'user'
    last_run_at     DATETIME,
    last_run_status TEXT,                -- success | failure | partial
    last_error      TEXT,
    run_count       INTEGER DEFAULT 0,
    avg_runtime_ms  REAL,
    token_cost_to_create  REAL,          -- one-time LLM cost to build this
    cumulative_run_cost   REAL DEFAULT 0, -- ongoing cost (should be ~0 for Python)
    flagged         BOOLEAN DEFAULT FALSE,
    flag_reason     TEXT
);

CREATE TABLE IF NOT EXISTS automation_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    automation_id   TEXT REFERENCES automations(id),
    run_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
    status          TEXT,                -- success | failure | partial
    runtime_ms      INTEGER,
    output_summary  TEXT,                -- structured JSON
    error_detail    TEXT,
    llm_tokens_used INTEGER DEFAULT 0,  -- should be 0 for normal runs
    reviewed_by_llm BOOLEAN DEFAULT FALSE,
    review_notes    TEXT
);

CREATE TABLE IF NOT EXISTS components (
    id              TEXT PRIMARY KEY,
    mcp_server_name TEXT NOT NULL,
    capability_id   TEXT NOT NULL,
    description     TEXT,
    input_schema    TEXT,                -- JSON schema
    output_schema   TEXT,                -- JSON schema
    usage_count     INTEGER DEFAULT 0,  -- how many automations use this
    tags            TEXT                 -- JSON array
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_automation_logs_automation_id
    ON automation_logs(automation_id);

CREATE INDEX IF NOT EXISTS idx_automation_logs_status
    ON automation_logs(status);

CREATE INDEX IF NOT EXISTS idx_automation_logs_run_at
    ON automation_logs(run_at);

CREATE INDEX IF NOT EXISTS idx_automations_status
    ON automations(status);

CREATE INDEX IF NOT EXISTS idx_components_mcp_server
    ON components(mcp_server_name);

CREATE INDEX IF NOT EXISTS idx_components_tags
    ON components(tags);
