"""
MCP Server Template.

Copy this directory to create a new dual-interface MCP server.
Rename the directory to your server name (e.g., youtube_analytics/).

Each server must:
1. Define Pydantic models for typed inputs/outputs
2. Implement core async functions callable by both Python and MCP
3. Register MCP tool wrappers that delegate to core functions
4. Include a manifest.yaml describing capabilities
5. Include tests for both calling patterns
"""
