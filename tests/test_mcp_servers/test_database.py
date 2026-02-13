"""Tests for the Database MCP Server.

Tests both calling patterns:
1. Direct Python function calls (the primary pattern)
2. Model validation and error handling
"""

import os
import tempfile

import pytest

from openfang.mcp_servers.database.server import (
    DeleteRequest,
    EnsureTableRequest,
    InsertRequest,
    QueryRequest,
    QueryResponse,
    UpsertRequest,
    WriteResponse,
    delete,
    ensure_table,
    insert,
    list_tables,
    query,
    upsert,
)


@pytest.fixture
def db_path(tmp_path):
    """Create a temporary database file for testing."""
    return str(tmp_path / "test.db")


@pytest.fixture
async def db_with_table(db_path):
    """Create a temp database with a users table."""
    await ensure_table(
        EnsureTableRequest(
            table="users",
            columns={
                "id": "TEXT PRIMARY KEY",
                "name": "TEXT NOT NULL",
                "email": "TEXT",
                "score": "INTEGER DEFAULT 0",
            },
        ),
        db_path=db_path,
    )
    return db_path


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

    def test_delete_request(self) -> None:
        req = DeleteRequest(table="users", where={"id": "1"})
        assert req.table == "users"
        assert req.where == {"id": "1"}

    def test_ensure_table_request(self) -> None:
        req = EnsureTableRequest(
            table="metrics",
            columns={"id": "TEXT", "value": "REAL"},
        )
        assert req.table == "metrics"
        assert req.columns["value"] == "REAL"


class TestEnsureTable:
    async def test_creates_table(self, db_path) -> None:
        result = await ensure_table(
            EnsureTableRequest(
                table="items",
                columns={"id": "TEXT PRIMARY KEY", "name": "TEXT"},
            ),
            db_path=db_path,
        )
        assert result.success is True

        tables = await list_tables(db_path=db_path)
        assert "items" in tables.tables

    async def test_idempotent(self, db_path) -> None:
        req = EnsureTableRequest(
            table="items",
            columns={"id": "TEXT PRIMARY KEY", "name": "TEXT"},
        )
        await ensure_table(req, db_path=db_path)
        result = await ensure_table(req, db_path=db_path)
        assert result.success is True

    async def test_rejects_invalid_table_name(self, db_path) -> None:
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            await ensure_table(
                EnsureTableRequest(
                    table="Robert'; DROP TABLE students;--",
                    columns={"id": "TEXT"},
                ),
                db_path=db_path,
            )


class TestListTables:
    async def test_empty_database(self, db_path) -> None:
        result = await list_tables(db_path=db_path)
        assert result.tables == []
        assert result.retrieved_at is not None

    async def test_lists_created_tables(self, db_with_table) -> None:
        result = await list_tables(db_path=db_with_table)
        assert "users" in result.tables


class TestInsert:
    async def test_insert_and_query(self, db_with_table) -> None:
        db = db_with_table

        result = await insert(
            InsertRequest(
                table="users",
                data={"id": "1", "name": "Alice", "email": "alice@test.com"},
            ),
            db_path=db,
        )
        assert result.success is True
        assert result.rows_affected == 1

        rows = await query(QueryRequest(table="users"), db_path=db)
        assert rows.count == 1
        assert rows.rows[0]["name"] == "Alice"

    async def test_insert_multiple_rows(self, db_with_table) -> None:
        db = db_with_table

        for i in range(5):
            await insert(
                InsertRequest(
                    table="users",
                    data={"id": str(i), "name": f"User {i}"},
                ),
                db_path=db,
            )

        rows = await query(QueryRequest(table="users"), db_path=db)
        assert rows.count == 5

    async def test_rejects_invalid_column_name(self, db_with_table) -> None:
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            await insert(
                InsertRequest(
                    table="users",
                    data={"id": "1", "bad column": "value"},
                ),
                db_path=db_with_table,
            )


class TestQuery:
    async def test_query_empty_table(self, db_with_table) -> None:
        result = await query(
            QueryRequest(table="users"),
            db_path=db_with_table,
        )
        assert result.count == 0
        assert result.rows == []
        assert result.retrieved_at is not None

    async def test_query_with_where(self, db_with_table) -> None:
        db = db_with_table

        await insert(
            InsertRequest(table="users", data={"id": "1", "name": "Alice"}),
            db_path=db,
        )
        await insert(
            InsertRequest(table="users", data={"id": "2", "name": "Bob"}),
            db_path=db,
        )

        result = await query(
            QueryRequest(table="users", where={"name": "Alice"}),
            db_path=db,
        )
        assert result.count == 1
        assert result.rows[0]["id"] == "1"

    async def test_query_with_limit(self, db_with_table) -> None:
        db = db_with_table

        for i in range(10):
            await insert(
                InsertRequest(table="users", data={"id": str(i), "name": f"User {i}"}),
                db_path=db,
            )

        result = await query(
            QueryRequest(table="users", limit=3),
            db_path=db,
        )
        assert result.count == 3

    async def test_query_with_order_by(self, db_with_table) -> None:
        db = db_with_table

        await insert(
            InsertRequest(table="users", data={"id": "1", "name": "Charlie", "score": 30}),
            db_path=db,
        )
        await insert(
            InsertRequest(table="users", data={"id": "2", "name": "Alice", "score": 10}),
            db_path=db,
        )
        await insert(
            InsertRequest(table="users", data={"id": "3", "name": "Bob", "score": 20}),
            db_path=db,
        )

        result = await query(
            QueryRequest(table="users", order_by="name ASC"),
            db_path=db,
        )
        assert result.rows[0]["name"] == "Alice"
        assert result.rows[2]["name"] == "Charlie"


class TestUpsert:
    async def test_upsert_insert(self, db_with_table) -> None:
        db = db_with_table

        result = await upsert(
            UpsertRequest(
                table="users",
                data={"id": "1", "name": "Alice", "email": "alice@test.com"},
                conflict_column="id",
            ),
            db_path=db,
        )
        assert result.success is True

        rows = await query(QueryRequest(table="users"), db_path=db)
        assert rows.count == 1
        assert rows.rows[0]["name"] == "Alice"

    async def test_upsert_update(self, db_with_table) -> None:
        db = db_with_table

        await insert(
            InsertRequest(
                table="users",
                data={"id": "1", "name": "Alice", "email": "old@test.com"},
            ),
            db_path=db,
        )

        await upsert(
            UpsertRequest(
                table="users",
                data={"id": "1", "name": "Alice Updated", "email": "new@test.com"},
                conflict_column="id",
            ),
            db_path=db,
        )

        rows = await query(QueryRequest(table="users"), db_path=db)
        assert rows.count == 1
        assert rows.rows[0]["name"] == "Alice Updated"
        assert rows.rows[0]["email"] == "new@test.com"


class TestDelete:
    async def test_delete_by_id(self, db_with_table) -> None:
        db = db_with_table

        await insert(
            InsertRequest(table="users", data={"id": "1", "name": "Alice"}),
            db_path=db,
        )
        await insert(
            InsertRequest(table="users", data={"id": "2", "name": "Bob"}),
            db_path=db,
        )

        result = await delete(
            DeleteRequest(table="users", where={"id": "1"}),
            db_path=db,
        )
        assert result.success is True
        assert result.rows_affected == 1

        rows = await query(QueryRequest(table="users"), db_path=db)
        assert rows.count == 1
        assert rows.rows[0]["name"] == "Bob"

    async def test_delete_nonexistent(self, db_with_table) -> None:
        result = await delete(
            DeleteRequest(table="users", where={"id": "999"}),
            db_path=db_with_table,
        )
        assert result.success is True
        assert result.rows_affected == 0


class TestSQLInjectionPrevention:
    async def test_rejects_table_injection(self, db_path) -> None:
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            await query(
                QueryRequest(table="users; DROP TABLE users"),
                db_path=db_path,
            )

    async def test_rejects_column_injection(self, db_with_table) -> None:
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            await query(
                QueryRequest(
                    table="users",
                    where={"1=1; --": "value"},
                ),
                db_path=db_with_table,
            )
