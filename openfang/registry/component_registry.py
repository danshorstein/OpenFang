"""
Component Registry — Index of available MCP server capabilities.

Discovers, indexes, and searches MCP server components by their
manifests. Used by the Codification Engine to find relevant
components when designing new pipelines.
"""

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("openfang.registry.component")


class ComponentRegistry:
    """
    Indexes all available MCP server capabilities.

    Reads manifest.yaml files from MCP server directories to build
    a searchable index of available components, their capabilities,
    input/output schemas, and tags.
    """

    def __init__(self, mcp_servers_dir: str = "openfang/mcp_servers") -> None:
        self.mcp_servers_dir = Path(mcp_servers_dir)
        self.components: list[dict[str, Any]] = []

    def discover(self) -> int:
        """
        Discover all MCP servers by reading their manifests.

        Scans the mcp_servers directory for manifest.yaml files
        and indexes their capabilities.

        Returns the number of components discovered.
        """
        self.components = []

        if not self.mcp_servers_dir.exists():
            logger.warning(f"MCP servers directory not found: {self.mcp_servers_dir}")
            return 0

        for manifest_path in self.mcp_servers_dir.glob("*/manifest.yaml"):
            server_name = manifest_path.parent.name
            if server_name.startswith("_"):
                continue  # Skip templates

            try:
                manifest = yaml.safe_load(manifest_path.read_text())
                self._index_manifest(server_name, manifest)
            except Exception as e:
                logger.error(f"Error reading manifest for {server_name}: {e}")

        logger.info(f"Discovered {len(self.components)} components")
        return len(self.components)

    def _index_manifest(
        self, server_name: str, manifest: dict[str, Any]
    ) -> None:
        """Index capabilities from a single manifest."""
        for capability in manifest.get("capabilities", []):
            component = {
                "id": f"{server_name}.{capability['id']}",
                "mcp_server_name": server_name,
                "capability_id": capability["id"],
                "description": capability.get("description", ""),
                "inputs": capability.get("inputs", []),
                "outputs": capability.get("outputs", {}),
                "tags": manifest.get("tags", []),
                "requires": manifest.get("requires", {}),
            }
            self.components.append(component)

    def search(
        self,
        tags: list[str] | None = None,
        capabilities: list[str] | None = None,
        query: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Search for components matching criteria.

        Args:
            tags: Filter by tags (any match).
            capabilities: Filter by capability IDs.
            query: Free-text search across names and descriptions.
        """
        results = self.components

        if tags:
            results = [
                c
                for c in results
                if any(tag in c.get("tags", []) for tag in tags)
            ]

        if capabilities:
            results = [
                c
                for c in results
                if c["capability_id"] in capabilities
            ]

        if query:
            query_lower = query.lower()
            results = [
                c
                for c in results
                if query_lower in c.get("description", "").lower()
                or query_lower in c.get("capability_id", "").lower()
                or query_lower in c.get("mcp_server_name", "").lower()
            ]

        return results

    def get_server_manifest(self, server_name: str) -> dict[str, Any] | None:
        """Load the full manifest for a specific MCP server."""
        manifest_path = self.mcp_servers_dir / server_name / "manifest.yaml"
        if not manifest_path.exists():
            return None

        return yaml.safe_load(manifest_path.read_text())

    def list_servers(self) -> list[str]:
        """List all discovered MCP server names."""
        return list(
            {c["mcp_server_name"] for c in self.components}
        )
