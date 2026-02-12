"""Tests for the Component Registry."""

import pytest

from openfang.registry.component_registry import ComponentRegistry


class TestComponentRegistry:
    def test_discover_finds_servers(self) -> None:
        registry = ComponentRegistry(mcp_servers_dir="openfang/mcp_servers")
        count = registry.discover()
        # Should find components from database, slack_notify, brave_search
        assert count > 0

    def test_search_by_tag(self) -> None:
        registry = ComponentRegistry(mcp_servers_dir="openfang/mcp_servers")
        registry.discover()

        results = registry.search(tags=["database"])
        assert len(results) > 0
        assert all("database" in r.get("tags", []) for r in results)

    def test_search_by_query(self) -> None:
        registry = ComponentRegistry(mcp_servers_dir="openfang/mcp_servers")
        registry.discover()

        results = registry.search(query="search")
        assert len(results) > 0

    def test_list_servers(self) -> None:
        registry = ComponentRegistry(mcp_servers_dir="openfang/mcp_servers")
        registry.discover()

        servers = registry.list_servers()
        assert "database" in servers
        assert "slack_notify" in servers
        assert "brave_search" in servers

    def test_empty_directory(self) -> None:
        registry = ComponentRegistry(mcp_servers_dir="nonexistent")
        count = registry.discover()
        assert count == 0
