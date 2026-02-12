"""
Agent connectivity framework for integrating Kimi with external systems.

This module provides the infrastructure for building connected agents that can:
- React to external events (webhooks, database changes, message queues)
- Communicate with other agents in a multi-agent system
- Manage persistent state across sessions
- Register and discover tools dynamically

Example:
    ```python
    from kimi_agent_sdk.connectors import EventBus, Event
    
    bus = EventBus()
    
    @bus.on("github.pr.created")
    async def handle_pr(event: Event):
        async for msg in prompt(f"Review: {event.data['diff']}"):
            await post_comment(msg)
    
    await bus.emit(Event(type="agent.ready", data={"status": "ok"}))
    ```
"""

from __future__ import annotations

from kimi_agent_sdk.connectors.events import Event, EventBus, EventHandler
from kimi_agent_sdk.connectors.state import StateManager, StateBackend, FileStateBackend, stateful

__all__ = [
    "Event",
    "EventBus",
    "EventHandler",
    "StateManager",
    "StateBackend",
    "FileStateBackend",
    "stateful",
]
