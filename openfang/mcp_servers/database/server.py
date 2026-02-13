"""
Database MCP Server

Provides typed database operations callable by both Python
orchestration scripts and LLM via MCP protocol.

Supports SQLite with a configurable database path. All functions
accept an optional db_path parameter for testability; when omitted
they fall back to the OPENFANG_DB_PATH environment variable.
"""

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

import aiosqlite
from pydantic import BaseModel

logger = logging.getLogger("openfang.mcp_servers.database")

# ── Configuration ──────────────────────────────────────────

_VALID_IDENTIFIER = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def _default_db_path() -> str:
    return os.environ.get("OPENFANG_DB_PATH", "openfang.db")


def _validate_identifier(name: str) -> str:
    """Validate a SQL identifier to prevent injection."""
    if not _VALID_IDENTIFIER.match(name):
        raise ValueError(f"Invalid SQL identifier: {name!r}")
    return name


# ── Typed Models ───────────────────────────────────────────


class QueryRequest(BaseModel):
    """Request to query records from a table."""

    table: str
    where: dict[str, Any] | None = None
    limit: int = 100
    order_by: str | None = None


class InsertRequest(BaseModel):
    """Request to insert a record into a table."""

    table: str
    data: dict[str, Any]


class UpsertRequest(BaseModel):
    """Request to insert or update a record."""

    table: str
    data: dict[str, Any]
    conflict_column: str = "id"


class DeleteRequest(BaseModel):
    """Request to delete records from a table."""

    table: str
    where: dict[str, Any]


class EnsureTableRequest(BaseModel):
    """Request to create a table if it doesn't exist."""

    table: str
    columns: dict[str, str]  # column_name -> SQL type (e.g. "TEXT", "INTEGER")


class QueryResponse(BaseModel):
    """Response containing query results."""

    rows: list[dict[str, Any]]
    count: int
    retrieved_at: datetime


class WriteResponse(BaseModel):
    """Response from a write operation."""

    success: bool
    rows_affected: int
    timestamp: datetime


class TableListResponse(BaseModel):
    """Response listing available tables."""

    tables: list[str]
    retrieved_at: datetime


# ── Core Functions (called by both MCP and Python) ─────────


async def ensure_table(
    request: EnsureTableRequest,
    db_path: str | None = None,
) -> WriteResponse:
    """
    Create a table if it doesn't already exist.

    Useful for pipelines that need to store data in a table
    that may not have been created yet.
    """
    db = db_path or _default_db_path()
    table = _validate_identifier(request.table)

    col_defs = []
    for col_name, col_type in request.columns.items():
        _validate_identifier(col_name)
        col_defs.append(f"{col_name} {col_type}")

    sql = f"CREATE TABLE IF NOT EXISTS {table} ({', '.join(col_defs)})"

    async with aiosqlite.connect(db) as conn:
        await conn.execute(sql)
        await conn.commit()

    logger.info(f"Ensured table exists: {table}")
    return WriteResponse(
        success=True,
        rows_affected=0,
        timestamp=datetime.now(timezone.utc),
    )


async def list_tables(db_path: str | None = None) -> TableListResponse:
    """List all user-created tables in the database."""
    db = db_path or _default_db_path()

    async with aiosqlite.connect(db) as conn:
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ) as cursor:
            rows = await cursor.fetchall()

    return TableListResponse(
        tables=[row[0] for row in rows],
        retrieved_at=datetime.now(timezone.utc),
    )


async def query(
    request: QueryRequest,
    db_path: str | None = None,
) -> QueryResponse:
    """
    Query records from a table with optional filtering.

    Builds a SELECT query from the typed request and returns
    matching rows as dictionaries.
    """
    db = db_path or _default_db_path()
    table = _validate_identifier(request.table)

    sql = f"SELECT * FROM {table}"
    params: list[Any] = []

    if request.where:
        conditions = []
        for key, value in request.where.items():
            _validate_identifier(key)
            conditions.append(f"{key} = ?")
            params.append(value)
        sql += " WHERE " + " AND ".join(conditions)

    if request.order_by:
        order_parts = request.order_by.strip().split()
        _validate_identifier(order_parts[0])
        if len(order_parts) > 1 and order_parts[1].upper() not in ("ASC", "DESC"):
            raise ValueError(f"Invalid ORDER BY direction: {order_parts[1]}")
        sql += f" ORDER BY {request.order_by}"

    sql += " LIMIT ?"
    params.append(request.limit)

    async with aiosqlite.connect(db) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(sql, params) as cursor:
            rows = [dict(row) for row in await cursor.fetchall()]

    return QueryResponse(
        rows=rows,
        count=len(rows),
        retrieved_at=datetime.now(timezone.utc),
    )


async def insert(
    request: InsertRequest,
    db_path: str | None = None,
) -> WriteResponse:
    """
    Insert a record into a table.

    Columns and values are extracted from the data dictionary.
    """
    db = db_path or _default_db_path()
    table = _validate_identifier(request.table)

    columns = list(request.data.keys())
    for col in columns:
        _validate_identifier(col)

    placeholders = ", ".join(["?"] * len(columns))
    col_names = ", ".join(columns)
    values = list(request.data.values())

    sql = f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})"

    async with aiosqlite.connect(db) as conn:
        cursor = await conn.execute(sql, values)
        await conn.commit()
        affected = cursor.rowcount

    return WriteResponse(
        success=True,
        rows_affected=affected,
        timestamp=datetime.now(timezone.utc),
    )


async def upsert(
    request: UpsertRequest,
    db_path: str | None = None,
) -> WriteResponse:
    """
    Insert or update a record based on a conflict column.

    If a record with the same conflict_column value exists,
    updates the other columns. Otherwise inserts a new record.
    """
    db = db_path or _default_db_path()
    table = _validate_identifier(request.table)
    _validate_identifier(request.conflict_column)

    columns = list(request.data.keys())
    for col in columns:
        _validate_identifier(col)

    placeholders = ", ".join(["?"] * len(columns))
    col_names = ", ".join(columns)
    values = list(request.data.values())

    update_cols = [c for c in columns if c != request.conflict_column]
    update_clause = ", ".join(f"{c} = excluded.{c}" for c in update_cols)

    sql = (
        f"INSERT INTO {table} ({col_names}) VALUES ({placeholders}) "
        f"ON CONFLICT({request.conflict_column}) DO UPDATE SET {update_clause}"
    )

    async with aiosqlite.connect(db) as conn:
        cursor = await conn.execute(sql, values)
        await conn.commit()
        affected = cursor.rowcount

    return WriteResponse(
        success=True,
        rows_affected=affected,
        timestamp=datetime.now(timezone.utc),
    )


async def delete(
    request: DeleteRequest,
    db_path: str | None = None,
) -> WriteResponse:
    """
    Delete records from a table matching the where clause.

    At least one where condition is required to prevent
    accidental full-table deletes.
    """
    db = db_path or _default_db_path()
    table = _validate_identifier(request.table)

    if not request.where:
        raise ValueError("DELETE requires at least one WHERE condition")

    conditions = []
    params: list[Any] = []
    for key, value in request.where.items():
        _validate_identifier(key)
        conditions.append(f"{key} = ?")
        params.append(value)

    sql = f"DELETE FROM {table} WHERE {' AND '.join(conditions)}"

    async with aiosqlite.connect(db) as conn:
        cursor = await conn.execute(sql, params)
        await conn.commit()
        affected = cursor.rowcount

    return WriteResponse(
        success=True,
        rows_affected=affected,
        timestamp=datetime.now(timezone.utc),
    )


# ── MCP Server Registration ───────────────────────────────

try:
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("database")

    @server.tool()
    async def mcp_query(
        table: str, where: str | None = None, limit: int = 100
    ) -> str:
        """Query records from a database table with optional JSON filter."""
        req = QueryRequest(
            table=table,
            where=json.loads(where) if where else None,
            limit=limit,
        )
        result = await query(req)
        return result.model_dump_json()

    @server.tool()
    async def mcp_insert(table: str, data: str) -> str:
        """Insert a record into a database table. Data is a JSON object."""
        req = InsertRequest(table=table, data=json.loads(data))
        result = await insert(req)
        return result.model_dump_json()

    @server.tool()
    async def mcp_upsert(
        table: str, data: str, conflict_column: str = "id"
    ) -> str:
        """Insert or update a record. Data is a JSON object."""
        req = UpsertRequest(
            table=table, data=json.loads(data), conflict_column=conflict_column
        )
        result = await upsert(req)
        return result.model_dump_json()

    @server.tool()
    async def mcp_delete(table: str, where: str) -> str:
        """Delete records from a table. Where is a JSON filter object."""
        req = DeleteRequest(table=table, where=json.loads(where))
        result = await delete(req)
        return result.model_dump_json()

    @server.tool()
    async def mcp_ensure_table(table: str, columns: str) -> str:
        """Create a table if it doesn't exist. Columns is a JSON {name: type} object."""
        req = EnsureTableRequest(table=table, columns=json.loads(columns))
        result = await ensure_table(req)
        return result.model_dump_json()

    @server.tool()
    async def mcp_list_tables() -> str:
        """List all tables in the database."""
        result = await list_tables()
        return result.model_dump_json()

except ImportError:
    server = None
