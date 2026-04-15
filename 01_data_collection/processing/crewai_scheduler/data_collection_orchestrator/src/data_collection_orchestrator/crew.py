from __future__ import annotations

from typing import List

from crewai import Agent, Crew, Process, Task
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai.project import CrewBase, agent, crew, task

from .tools.brightdata_mcp_entry import BrightDataMCPEntryTool


@CrewBase
class DataCollectionOrchestratorCrew:
    """Minimal CrewAI crew aligned to Bright Data MCP entry."""

    agents: List[BaseAgent]
    tasks: List[Task]

    @agent
    def research_coordinator(self) -> Agent:
        return Agent(
            config=self.agents_config["research_coordinator"],
            verbose=True,
        )

    @agent
    def web_collection_specialist(self) -> Agent:
        return Agent(
            config=self.agents_config["web_collection_specialist"],
            verbose=True,
            tools=[BrightDataMCPEntryTool()],
        )

    @task
    def plan_collection_task(self) -> Task:
        return Task(config=self.tasks_config["plan_collection_task"])

    @task
    def collect_with_mcp_task(self) -> Task:
        return Task(config=self.tasks_config["collect_with_mcp_task"])

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
        )
