"""Tests for the Component Registry.

Validates that the registry correctly discovers and indexes
MCP server manifests, and that search/filtering works across
all three reference servers.
"""

import pytest

from openfang.registry.component_registry import ComponentRegistry


@pytest.fixture
def registry():
    """Pre-discovered component registry."""
    reg = ComponentRegistry(mcp_servers_dir="openfang/mcp_servers")
    reg.discover()
    return reg


class TestDiscovery:
    def test_discover_finds_servers(self) -> None:
        registry = ComponentRegistry(mcp_servers_dir="openfang/mcp_servers")
        count = registry.discover()
        # database (6) + slack_notify (2) + brave_search (1) = 9+ capabilities
        assert count >= 9

    def test_skips_template_directory(self) -> None:
        registry = ComponentRegistry(mcp_servers_dir="openfang/mcp_servers")
        registry.discover()

        server_names = {c["mcp_server_name"] for c in registry.components}
        assert "_template" not in server_names

    def test_empty_directory(self) -> None:
        registry = ComponentRegistry(mcp_servers_dir="nonexistent")
        count = registry.discover()
        assert count == 0

    def test_rediscover_clears_old(self) -> None:
        registry = ComponentRegistry(mcp_servers_dir="openfang/mcp_servers")
        first_count = registry.discover()
        second_count = registry.discover()
        assert first_count == second_count


class TestListServers:
    def test_lists_all_three_servers(self, registry) -> None:
        servers = registry.list_servers()
        assert "database" in servers
        assert "slack_notify" in servers
        assert "brave_search" in servers

    def test_no_duplicates(self, registry) -> None:
        servers = registry.list_servers()
        assert len(servers) == len(set(servers))


class TestSearchByTag:
    def test_search_database_tag(self, registry) -> None:
        results = registry.search(tags=["database"])
        assert len(results) > 0
        assert all("database" in r.get("tags", []) for r in results)

    def test_search_messaging_tag(self, registry) -> None:
        results = registry.search(tags=["messaging"])
        assert len(results) > 0
        assert all(r["mcp_server_name"] == "slack_notify" for r in results)

    def test_search_nonexistent_tag(self, registry) -> None:
        results = registry.search(tags=["nonexistent_tag"])
        assert len(results) == 0

    def test_search_multiple_tags_or(self, registry) -> None:
        results = registry.search(tags=["database", "search"])
        assert len(results) > 0
        # Should include both database and brave_search components
        servers = {r["mcp_server_name"] for r in results}
        assert "database" in servers
        assert "brave_search" in servers


class TestSearchByCapability:
    def test_search_query_capability(self, registry) -> None:
        results = registry.search(capabilities=["query"])
        assert len(results) == 1
        assert results[0]["mcp_server_name"] == "database"

    def test_search_send_message_capability(self, registry) -> None:
        results = registry.search(capabilities=["send_message"])
        assert len(results) == 1
        assert results[0]["mcp_server_name"] == "slack_notify"

    def test_search_search_capability(self, registry) -> None:
        results = registry.search(capabilities=["search"])
        assert len(results) == 1
        assert results[0]["mcp_server_name"] == "brave_search"


class TestSearchByQuery:
    def test_free_text_search(self, registry) -> None:
        results = registry.search(query="search")
        assert len(results) > 0

    def test_search_by_description(self, registry) -> None:
        results = registry.search(query="slack")
        assert len(results) > 0
        assert any(r["mcp_server_name"] == "slack_notify" for r in results)

    def test_case_insensitive(self, registry) -> None:
        lower = registry.search(query="database")
        upper = registry.search(query="DATABASE")
        assert len(lower) == len(upper)


class TestComponentStructure:
    def test_component_has_required_fields(self, registry) -> None:
        for component in registry.components:
            assert "id" in component
            assert "mcp_server_name" in component
            assert "capability_id" in component
            assert "description" in component
            assert "tags" in component

    def test_component_id_format(self, registry) -> None:
        for component in registry.components:
            # ID should be "server_name.capability_id"
            assert "." in component["id"]
            parts = component["id"].split(".")
            assert parts[0] == component["mcp_server_name"]
            assert parts[1] == component["capability_id"]


class TestGetManifest:
    def test_get_existing_manifest(self, registry) -> None:
        manifest = registry.get_server_manifest("database")
        assert manifest is not None
        assert manifest["name"] == "database"
        assert "capabilities" in manifest

    def test_get_nonexistent_manifest(self, registry) -> None:
        manifest = registry.get_server_manifest("nonexistent")
        assert manifest is None
