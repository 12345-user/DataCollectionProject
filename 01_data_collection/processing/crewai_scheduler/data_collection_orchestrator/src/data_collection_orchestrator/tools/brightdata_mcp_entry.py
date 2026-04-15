from __future__ import annotations

import os
from pathlib import Path
from typing import Type

from pydantic import BaseModel, Field

from crewai.tools import BaseTool


class BrightDataMCPInput(BaseModel):
    objective: str = Field(..., description="Collection objective for this run")


class BrightDataMCPEntryTool(BaseTool):
    name: str = "brightdata_mcp_entry"
    description: str = (
        "Shows the Bright Data MCP launch command configured for this project. "
        "Use this as the integration handoff from CrewAI to MCP runtime."
    )
    args_schema: Type[BaseModel] = BrightDataMCPInput

    def _run(self, objective: str) -> str:
        mcp_workdir = os.getenv(
            "BRIGHTDATA_MCP_WORKDIR",
            "../brightdata_mcp_connector/service",
        )
        mcp_command = os.getenv("BRIGHTDATA_MCP_COMMAND", "npx")
        mcp_args = os.getenv("BRIGHTDATA_MCP_ARGS", "@brightdata/mcp")
        resolved = Path(mcp_workdir).resolve()
        return (
            f"Objective: {objective}\n"
            f"MCP workdir: {resolved}\n"
            f"Launch command: {mcp_command} {mcp_args}\n"
            "Ensure API_TOKEN is set in Bright Data MCP .env before execution."
        )
