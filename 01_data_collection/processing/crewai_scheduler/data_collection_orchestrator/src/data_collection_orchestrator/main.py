from __future__ import annotations

from .crew import DataCollectionOrchestratorCrew


def run() -> None:
    inputs = {"topic": "enterprise technology landscape"}
    DataCollectionOrchestratorCrew().crew().kickoff(inputs=inputs)


if __name__ == "__main__":
    run()
