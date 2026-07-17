"""Isolated AI Agent service package."""

__all__ = ["agent_service"]


def __getattr__(name: str):
    if name == "agent_service":
        from services.agent.service import agent_service

        return agent_service
    raise AttributeError(name)
