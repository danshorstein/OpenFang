"""
Database MCP Server

Provides typed database operations callable by both Python
orchestration scripts and LLM via MCP protocol.

Supports SQLite (default) with a path configurable via
OPENFANG_DB_PATH environment variable.
"""

import json
import os
from datetime import datetime, timezone
from typing import Any

import aiosqlite
from pydantic import BaseModel


# ── Configuration ──────────────────────────────────────────

DB_PATH = os.environ.get("OPENFANG_DB_PATH", "openfang.db")


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


# ── Core Functions (called by both MCP and Python) ─────────


async def query(request: QueryRequest) -> QueryResponse:
    """
    Query records from a table with optional filtering.

    Builds a SELECT query from the typed request and returns
    matching rows as dictionaries.
    """
    sql = f"SELECT * FROM {request.table}"  # noqa: S608
    params: list[Any] = []

    if request.where:
        conditions = []
        for key, value in request.where.items():
            conditions.append(f"{key} = ?")
            params.append(value)
        sql += " WHERE " + " AND ".join(conditions)

    if request.order_by:
        sql += f" ORDER BY {request.order_by}"

    sql += f" LIMIT {request.limit}"

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(sql, params) as cursor:
            rows = [dict(row) for row in await cursor.fetchall()]

    return QueryResponse(
        rows=rows,
        count=len(rows),
        retrieved_at=datetime.now(timezone.utc),
    )


async def insert(request: InsertRequest) -> WriteResponse:
    """
    Insert a record into a table.

    Columns and values are extracted from the data dictionary.
    """
    columns = list(request.data.keys())
    placeholders = ", ".join(["?"] * len(columns))
    col_names = ", ".join(columns)
    values = list(request.data.values())

    sql = f"INSERT INTO {request.table} ({col_names}) VALUES ({placeholders})"

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(sql, values)
        await db.commit()

    return WriteResponse(
        success=True,
        rows_affected=cursor.rowcount,
        timestamp=datetime.now(timezone.utc),
    )


async def upsert(request: UpsertRequest) -> WriteResponse:
    """
    Insert or update a record based on a conflict column.

    If a record with the same conflict_column value exists,
    updates the other columns. Otherwise inserts a new record.
    """
    columns = list(request.data.keys())
    placeholders = ", ".join(["?"] * len(columns))
    col_names = ", ".join(columns)
    values = list(request.data.values())

    update_cols = [c for c in columns if c != request.conflict_column]
    update_clause = ", ".join(f"{c} = excluded.{c}" for c in update_cols)

    sql = (
        f"INSERT INTO {request.table} ({col_names}) VALUES ({placeholders}) "
        f"ON CONFLICT({request.conflict_column}) DO UPDATE SET {update_clause}"
    )

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(sql, values)
        await db.commit()

    return WriteResponse(
        success=True,
        rows_affected=cursor.rowcount,
        timestamp=datetime.now(timezone.utc),
    )


# ── MCP Server Registration ───────────────────────────────

try:
    from mcp.server import Server

    server = Server("database")

    @server.tool()
    async def mcp_query(table: str, where: str | None = None, limit: int = 100) -> str:
        """Query records from a database table with optional JSON filter."""
        request = QueryRequest(
            table=table,
            where=json.loads(where) if where else None,
            limit=limit,
        )
        result = await query(request)
        return result.model_dump_json()

    @server.tool()
    async def mcp_insert(table: str, data: str) -> str:
        """Insert a record into a database table. Data is a JSON object."""
        request = InsertRequest(table=table, data=json.loads(data))
        result = await insert(request)
        return result.model_dump_json()

    @server.tool()
    async def mcp_upsert(
        table: str, data: str, conflict_column: str = "id"
    ) -> str:
        """Insert or update a record. Data is a JSON object."""
        request = UpsertRequest(
            table=table, data=json.loads(data), conflict_column=conflict_column
        )
        result = await upsert(request)
        return result.model_dump_json()

except ImportError:
    server = None
