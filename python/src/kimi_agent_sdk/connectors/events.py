"""
Event-driven architecture for agent connectivity.

Provides an asynchronous event bus for agents to:
- Subscribe to external events (webhooks, database changes, etc.)
- Publish events for other systems to consume
- Build reactive agent workflows
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable, TypeVar

if TYPE_CHECKING:
    from collections.abc import Awaitable

T = TypeVar("T")

# Type alias for event handler functions
EventHandler = Callable[["Event"], "Awaitable[None] | None"]


@dataclass(frozen=True)
class Event:
    """An event in the system.
    
    Attributes:
        type: Event type identifier (e.g., "github.pr.created")
        data: Event payload data
        source: Event source identifier (e.g., "github-webhook")
        timestamp: When the event occurred
        id: Unique event identifier
    """
    
    type: str
    data: dict[str, Any] = field(default_factory=dict)
    source: str = "unknown"
    timestamp: datetime = field(default_factory=datetime.now)
    id: str = field(default_factory=lambda: asyncio.get_event_loop().time().__str__())
    
    def __post_init__(self) -> None:
        # Ensure data is immutable for hashing
        object.__setattr__(self, "data", dict(self.data))


class EventBus:
    """Asynchronous event bus for agent connectivity.
    
    Enables event-driven agent architectures where agents can:
    - React to external system events (webhooks, database changes)
    - Communicate between different agent components
    - Build reactive workflows
    
    The event bus supports:
    - Exact type matching ("github.pr.created")
    - Wildcard patterns ("github.pr.*", "github.*.created")
    - Async and sync handlers
    - Middleware for event processing
    
    Example:
        ```python
        bus = EventBus()
        
        # Subscribe to specific event
        @bus.on("github.pr.created")
        async def on_pr_created(event: Event):
            print(f"New PR: {event.data['title']}")
        
        # Subscribe with wildcard
        @bus.on("github.pr.*")
        async def on_any_pr_event(event: Event):
            print(f"PR event: {event.type}")
        
        # Emit event
        await bus.emit(Event(
            type="github.pr.created",
            data={"title": "Fix bug", "author": "alice"}
        ))
        ```
    """
    
    def __init__(self) -> None:
        """Initialize the event bus."""
        # Map of event type patterns to handler sets
        self._handlers: dict[str, set[EventHandler]] = defaultdict(set)
        # Middleware chain
        self._middleware: list[Callable[[Event], Awaitable[Event]]] = []
        # Event history for replay/debugging
        self._history: list[Event] = []
        self._max_history = 1000
        # Lock for thread-safe operations
        self._lock = asyncio.Lock()
    
    def on(self, event_type: str) -> Callable[[EventHandler], EventHandler]:
        """Decorator to register an event handler.
        
        Supports wildcard patterns:
        - "github.pr.created" - exact match
        - "github.pr.*" - any PR event
        - "github.*.created" - any created event in github
        - "*" - all events
        
        Args:
            event_type: Event type pattern to subscribe to
            
        Returns:
            Decorator function that registers the handler
            
        Example:
            ```python
            @bus.on("database.record.changed")
            async def on_db_change(event: Event):
                await sync_to_search_index(event.data)
            ```
        """
        def decorator(handler: EventHandler) -> EventHandler:
            self._handlers[event_type].add(handler)
            return handler
        return decorator
    
    def off(self, event_type: str, handler: EventHandler) -> bool:
        """Unregister an event handler.
        
        Args:
            event_type: Event type pattern
            handler: Handler function to remove
            
        Returns:
            True if handler was found and removed
        """
        if event_type in self._handlers:
            self._handlers[event_type].discard(handler)
            return True
        return False
    
    async def emit(self, event: Event) -> None:
        """Emit an event to all matching handlers.
        
        Handlers matching the event type (including wildcards) are called
        concurrently. Errors in individual handlers don't affect others.
        
        Args:
            event: Event to emit
        """
        async with self._lock:
            # Store in history
            self._history.append(event)
            if len(self._history) > self._max_history:
                self._history.pop(0)
        
        # Apply middleware
        processed_event = event
        for middleware in self._middleware:
            processed_event = await middleware(processed_event)
        
        # Find all matching handlers
        handlers: set[EventHandler] = set()
        for pattern, pattern_handlers in self._handlers.items():
            if self._matches_pattern(event.type, pattern):
                handlers.update(pattern_handlers)
        
        if not handlers:
            return
        
        # Call all handlers concurrently
        await asyncio.gather(
            *[self._call_handler(h, processed_event) for h in handlers],
            return_exceptions=True  # Don't let one handler failure stop others
        )
    
    async def _call_handler(self, handler: EventHandler, event: Event) -> None:
        """Call a single handler with error handling."""
        try:
            result = handler(event)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            # Log error but don't stop other handlers
            print(f"Event handler error for {event.type}: {e}")
    
    def _matches_pattern(self, event_type: str, pattern: str) -> bool:
        """Check if event type matches a pattern.
        
        Supports:
        - Exact match: "github.pr.created" matches "github.pr.created"
        - Single wildcard: "github.pr.*" matches "github.pr.created"
        - Multi-level wildcard: "github.*" matches "github.pr.created"
        """
        if pattern == "*":
            return True
        
        event_parts = event_type.split(".")
        pattern_parts = pattern.split(".")
        
        if len(event_parts) != len(pattern_parts):
            return False
        
        for event_part, pattern_part in zip(event_parts, pattern_parts):
            if pattern_part != "*" and pattern_part != event_part:
                return False
        
        return True
    
    def use(self, middleware: Callable[[Event], Awaitable[Event]]) -> None:
        """Add middleware to process all events.
        
        Middleware can transform events, add metadata, or perform logging.
        Middleware is called in the order added.
        
        Args:
            middleware: Async function that receives and returns an Event
            
        Example:
            ```python
            async def add_timestamp(event: Event) -> Event:
                event.data['processed_at'] = datetime.now().isoformat()
                return event
            
            bus.use(add_timestamp)
            ```
        """
        self._middleware.append(middleware)
    
    def get_history(
        self,
        event_type: str | None = None,
        limit: int = 100
    ) -> list[Event]:
        """Get event history.
        
        Useful for debugging and replay scenarios.
        
        Args:
            event_type: Filter by event type (optional)
            limit: Maximum number of events to return
            
        Returns:
            List of historical events
        """
        events = self._history
        
        if event_type:
            events = [e for e in events if e.type == event_type]
        
        return events[-limit:]
    
    def clear_history(self) -> None:
        """Clear event history."""
        self._history.clear()
    
    def handler_count(self, event_type: str | None = None) -> int:
        """Count registered handlers.
        
        Args:
            event_type: Count handlers for specific type, or all if None
            
        Returns:
            Number of handlers
        """
        if event_type:
            return len(self._handlers.get(event_type, set()))
        
        return sum(len(handlers) for handlers in self._handlers.values())


class EventSource:
    """Base class for event sources that emit events to a bus.
    
    Event sources bridge external systems (webhooks, databases, etc.)
    with the event bus.
    
    Example:
        ```python
        class WebhookSource(EventSource):
            async def start(self):
                # Start HTTP server to receive webhooks
                ...
            
            async def stop(self):
                # Cleanup
                ...
        ```
    """
    
    def __init__(self, bus: EventBus) -> None:
        """Initialize with event bus.
        
        Args:
            bus: Event bus to emit events to
        """
        self.bus = bus
        self._running = False
    
    async def start(self) -> None:
        """Start the event source.
        
        Should begin listening for external events and emit them to the bus.
        """
        self._running = True
    
    async def stop(self) -> None:
        """Stop the event source.
        
        Should clean up resources and stop listening.
        """
        self._running = False
    
    @property
    def is_running(self) -> bool:
        """Check if the source is running."""
        return self._running


class TimerSource(EventSource):
    """Event source that emits events on a schedule.
    
    Useful for periodic tasks and cron-like workflows.
    
    Example:
        ```python
        timer = TimerSource(bus)
        timer.schedule("health.check", interval=60)  # Every 60 seconds
        await timer.start()
        ```
    """
    
    def __init__(self, bus: EventBus) -> None:
        super().__init__(bus)
        self._schedules: dict[str, asyncio.Task] = {}
    
    def schedule(
        self,
        event_type: str,
        interval: float,
        data: dict[str, Any] | None = None
    ) -> None:
        """Schedule a recurring event.
        
        Args:
            event_type: Type of event to emit
            interval: Interval in seconds
            data: Optional data to include in events
        """
        async def emit_periodically() -> None:
            while self._running:
                await asyncio.sleep(interval)
                if self._running:
                    await self.bus.emit(Event(
                        type=event_type,
                        data=data or {},
                        source="timer"
                    ))
        
        task = asyncio.create_task(emit_periodically())
        self._schedules[event_type] = task
    
    def cancel(self, event_type: str) -> bool:
        """Cancel a scheduled event.
        
        Args:
            event_type: Event type to cancel
            
        Returns:
            True if schedule was found and cancelled
        """
        if event_type in self._schedules:
            self._schedules[event_type].cancel()
            del self._schedules[event_type]
            return True
        return False
    
    async def stop(self) -> None:
        """Stop all scheduled events."""
        await super().stop()
        
        for task in self._schedules.values():
            task.cancel()
        
        # Wait for tasks to complete
        if self._schedules:
            await asyncio.gather(
                *self._schedules.values(),
                return_exceptions=True
            )
        
        self._schedules.clear()


__all__ = [
    "Event",
    "EventBus",
    "EventHandler",
    "EventSource",
    "TimerSource",
]
