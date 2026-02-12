"""
OpenFang Registry — Automation and component tracking.

SQLite-backed stores for tracking deployed automations,
their run history, and available MCP server capabilities.
"""

from openfang.registry.automation_registry import AutomationRegistry
from openfang.registry.component_registry import ComponentRegistry

__all__ = ["AutomationRegistry", "ComponentRegistry"]
