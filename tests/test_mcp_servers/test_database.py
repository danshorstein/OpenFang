"""Tests for the Database MCP Server."""

import pytest

from openfang.mcp_servers.database.server import (
    InsertRequest,
    QueryRequest,
    QueryResponse,
    UpsertRequest,
    WriteResponse,
)


class TestDatabaseModels:
    def test_query_request_defaults(self) -> None:
        req = QueryRequest(table="test_table")
        assert req.table == "test_table"
        assert req.where is None
        assert req.limit == 100
        assert req.order_by is None

    def test_query_request_with_filter(self) -> None:
        req = QueryRequest(
            table="users",
            where={"email": "test@example.com"},
            limit=10,
        )
        assert req.where == {"email": "test@example.com"}

    def test_insert_request(self) -> None:
        req = InsertRequest(
            table="users",
            data={"name": "Alice", "email": "alice@example.com"},
        )
        assert req.table == "users"
        assert req.data["name"] == "Alice"

    def test_upsert_request_default_conflict(self) -> None:
        req = UpsertRequest(
            table="users",
            data={"id": "1", "name": "Alice"},
        )
        assert req.conflict_column == "id"
