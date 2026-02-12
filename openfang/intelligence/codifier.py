"""
Codification Engine — Converts user requests into deployed Python automations.

This is the core of OpenFang's philosophy: the LLM designs and writes
the automation once, then Python runs it forever.

Process:
1. Parse intent from user message
2. Discover relevant MCP servers via manifests
3. Design pipeline (which servers, what order, what logic)
4. Generate Python orchestration script
5. Generate documentation
6. Test in sandbox
7. Deploy to orchestration layer
8. Register in automations registry
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from openfang.intelligence.models import LLMClient, LLMTier
from openfang.orchestration.sandbox import Sandbox

logger = logging.getLogger("openfang.intelligence.codifier")


@dataclass
class ParsedIntent:
    """Structured representation of what the user wants to automate."""

    summary: str
    required_capabilities: list[str]
    relevant_tags: list[str]
    suggested_schedule: str | None = None
    data_sources: list[str] = field(default_factory=list)
    output_targets: list[str] = field(default_factory=list)


@dataclass
class PipelineDesign:
    """The LLM's design for a new automation pipeline."""

    name: str
    description: str
    steps: list[dict[str, Any]]
    mcp_servers_used: list[str]
    cron_schedule: str | None = None
    config_params: dict[str, Any] = field(default_factory=dict)


class CodificationEngine:
    """
    Converts user requests into deployed Python automations.

    The codification process:
    1. Understand what the user wants (intent parsing)
    2. Find relevant MCP server components
    3. Design the pipeline architecture
    4. Generate executable Python code
    5. Test in sandbox
    6. Deploy and register
    """

    def __init__(
        self,
        llm_client: LLMClient,
        component_registry: Any,
        automation_registry: Any,
        sandbox: Sandbox | None = None,
    ) -> None:
        self.llm_client = llm_client
        self.component_registry = component_registry
        self.automation_registry = automation_registry
        self.sandbox = sandbox or Sandbox()

    async def codify(
        self,
        user_request: str,
        llm_tier: LLMTier = LLMTier.SONNET,
    ) -> str:
        """
        Full codification pipeline: request → deployed automation.

        Returns the automation_id of the newly created automation,
        or an error message if codification failed.
        """
        # Step 1: Understand what the user wants
        intent = await self.parse_intent(user_request, llm_tier)
        logger.info(f"Parsed intent: {intent.summary}")

        # Step 2: Find relevant components
        available_components = self.component_registry.search(
            tags=intent.relevant_tags,
            capabilities=intent.required_capabilities,
        )
        logger.info(f"Found {len(available_components)} relevant components")

        # Step 3: Design the pipeline
        design = await self.design_pipeline(
            intent=intent,
            components=available_components,
            llm_tier=llm_tier,
        )
        logger.info(f"Designed pipeline: {design.name}")

        # Step 4: Generate the Python script
        script = await self.generate_script(design=design, llm_tier=llm_tier)

        # Step 5: Sandbox test
        test_result = await self.sandbox.test(script)
        if not test_result.passed:
            logger.warning(f"Sandbox test failed: {test_result.errors}")
            # Attempt to patch
            script = await self._patch_script(
                script, test_result.errors, llm_tier
            )
            test_result = await self.sandbox.test(script)
            if not test_result.passed:
                return f"Failed to create automation: {test_result.errors}"

        # Step 6: Deploy and register
        automation_id = self._generate_id(design.name)
        self.automation_registry.register(
            id=automation_id,
            name=design.name,
            description=design.description,
            pipeline_file=script,
            cron_schedule=design.cron_schedule,
            mcp_servers=design.mcp_servers_used,
        )

        logger.info(f"Deployed automation: {automation_id}")
        return automation_id

    async def parse_intent(
        self, user_request: str, llm_tier: LLMTier
    ) -> ParsedIntent:
        """Parse user request into structured intent."""
        system = """You are an automation architect. Parse the user's request
into a structured intent. Identify:
- What data sources are needed
- What the output/action should be
- What schedule makes sense (cron expression)
- What capabilities are required

Respond as structured text with clear sections."""

        response = await self.llm_client.complete(
            prompt=user_request,
            tier=llm_tier,
            system=system,
        )

        # TODO: Parse LLM response into structured ParsedIntent
        return ParsedIntent(
            summary=user_request,
            required_capabilities=[],
            relevant_tags=[],
        )

    async def design_pipeline(
        self,
        intent: ParsedIntent,
        components: list[dict[str, Any]],
        llm_tier: LLMTier,
    ) -> PipelineDesign:
        """Design the pipeline architecture using available components."""
        component_descriptions = "\n".join(
            f"- {c.get('name', 'unknown')}: {c.get('description', '')}"
            for c in components
        )

        system = """You are a pipeline architect. Given a user intent and
available MCP server components, design a pipeline that:
1. Uses existing components where possible
2. Chains steps in a logical order
3. Includes error handling strategy
4. Suggests an appropriate cron schedule"""

        prompt = f"""Intent: {intent.summary}

Available components:
{component_descriptions}

Design the pipeline."""

        response = await self.llm_client.complete(
            prompt=prompt,
            tier=llm_tier,
            system=system,
        )

        # TODO: Parse LLM response into structured PipelineDesign
        return PipelineDesign(
            name=intent.summary[:50].replace(" ", "_").lower(),
            description=intent.summary,
            steps=[],
            mcp_servers_used=[],
        )

    async def generate_script(
        self,
        design: PipelineDesign,
        llm_tier: LLMTier,
    ) -> str:
        """Generate a Python pipeline script from the design."""
        system = """You are a Python code generator for OpenFang pipelines.
Generate a complete, runnable Python script that:
1. Imports from openfang.mcp_servers.* for all MCP operations
2. Has an async def run(context) entry point
3. Uses context.config for configuration
4. Returns context.success(summary=...) or context.failure(summary=...)
5. Includes comprehensive docstring and logging
6. Handles errors gracefully"""

        prompt = f"""Pipeline: {design.name}
Description: {design.description}
Steps: {design.steps}
MCP Servers: {design.mcp_servers_used}
Schedule: {design.cron_schedule}

Generate the complete Python script."""

        response = await self.llm_client.complete(
            prompt=prompt,
            tier=llm_tier,
            system=system,
        )

        # TODO: Extract Python code from LLM response and write to file
        return response.content

    async def _patch_script(
        self,
        script: str,
        errors: list[str],
        llm_tier: LLMTier,
    ) -> str:
        """Attempt to fix a script that failed sandbox testing."""
        prompt = f"""This Python pipeline script failed sandbox testing.

Script:
{script}

Errors:
{errors}

Fix the script and return the corrected version."""

        response = await self.llm_client.complete(
            prompt=prompt,
            tier=llm_tier,
        )

        return response.content

    def _generate_id(self, name: str) -> str:
        """Generate a unique automation ID from a name."""
        import hashlib
        from datetime import datetime, timezone

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        name_slug = name[:30].replace(" ", "_").lower()
        hash_suffix = hashlib.sha256(
            f"{name}{timestamp}".encode()
        ).hexdigest()[:8]
        return f"{name_slug}_{hash_suffix}"
