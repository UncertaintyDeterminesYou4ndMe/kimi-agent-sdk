"""Tests for agent connectivity framework."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest

from kimi_agent_sdk.connectors import Event, EventBus, StateManager, FileStateBackend
from kimi_agent_sdk.connectors.events import TimerSource


class TestEvent:
    """Tests for Event dataclass."""

    def test_event_creation(self) -> None:
        """Test basic event creation."""
        event = Event(
            type="test.event",
            data={"key": "value"},
            source="test"
        )
        
        assert event.type == "test.event"
        assert event.data == {"key": "value"}
        assert event.source == "test"
        assert event.id is not None
        assert event.timestamp is not None

    def test_event_defaults(self) -> None:
        """Test event default values."""
        event = Event(type="test.event")
        
        assert event.data == {}
        assert event.source == "unknown"


class TestEventBus:
    """Tests for EventBus."""

    @pytest.mark.asyncio
    async def test_emit_and_handle(self) -> None:
        """Test basic emit and handle flow."""
        bus = EventBus()
        received_events = []
        
        @bus.on("test.event")
        def handler(event: Event) -> None:
            received_events.append(event)
        
        await bus.emit(Event(type="test.event", data={"test": True}))
        
        assert len(received_events) == 1
        assert received_events[0].type == "test.event"
        assert received_events[0].data["test"] is True

    @pytest.mark.asyncio
    async def test_async_handler(self) -> None:
        """Test async event handler."""
        bus = EventBus()
        received = []
        
        @bus.on("test.event")
        async def handler(event: Event) -> None:
            await asyncio.sleep(0.01)
            received.append(event)
        
        await bus.emit(Event(type="test.event"))
        
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_wildcard_handler(self) -> None:
        """Test wildcard pattern matching."""
        bus = EventBus()
        received = []
        
        @bus.on("test.*")
        def handler(event: Event) -> None:
            received.append(event.type)
        
        await bus.emit(Event(type="test.event1"))
        await bus.emit(Event(type="test.event2"))
        await bus.emit(Event(type="other.event"))  # Should not match
        
        assert len(received) == 2
        assert "test.event1" in received
        assert "test.event2" in received

    @pytest.mark.asyncio
    async def test_multiple_handlers(self) -> None:
        """Test multiple handlers for same event."""
        bus = EventBus()
        handler1_called = False
        handler2_called = False
        
        @bus.on("test.event")
        def handler1(event: Event) -> None:
            nonlocal handler1_called
            handler1_called = True
        
        @bus.on("test.event")
        def handler2(event: Event) -> None:
            nonlocal handler2_called
            handler2_called = True
        
        await bus.emit(Event(type="test.event"))
        
        assert handler1_called
        assert handler2_called

    @pytest.mark.asyncio
    async def test_handler_error_isolation(self) -> None:
        """Test that one handler error doesn't affect others."""
        bus = EventBus()
        handler2_called = False
        
        @bus.on("test.event")
        def failing_handler(event: Event) -> None:
            raise Exception("Handler error")
        
        @bus.on("test.event")
        def success_handler(event: Event) -> None:
            nonlocal handler2_called
            handler2_called = True
        
        # Should not raise
        await bus.emit(Event(type="test.event"))
        
        assert handler2_called

    @pytest.mark.asyncio
    async def test_off_removes_handler(self) -> None:
        """Test removing event handler."""
        bus = EventBus()
        received = []
        
        def handler(event: Event) -> None:
            received.append(event)
        
        bus.on("test.event")(handler)
        await bus.emit(Event(type="test.event"))
        
        bus.off("test.event", handler)
        await bus.emit(Event(type="test.event"))
        
        assert len(received) == 1

    def test_handler_count(self) -> None:
        """Test counting registered handlers."""
        bus = EventBus()
        
        @bus.on("event1")
        def handler1(event: Event) -> None:
            pass
        
        @bus.on("event1")
        def handler2(event: Event) -> None:
            pass
        
        @bus.on("event2")
        def handler3(event: Event) -> None:
            pass
        
        assert bus.handler_count("event1") == 2
        assert bus.handler_count("event2") == 1
        assert bus.handler_count() == 3

    @pytest.mark.asyncio
    async def test_history_tracking(self) -> None:
        """Test event history."""
        bus = EventBus()
        
        await bus.emit(Event(type="event1", data={"a": 1}))
        await bus.emit(Event(type="event2", data={"b": 2}))
        await bus.emit(Event(type="event1", data={"c": 3}))
        
        history = bus.get_history()
        assert len(history) == 3
        
        filtered = bus.get_history(event_type="event1")
        assert len(filtered) == 2

    @pytest.mark.asyncio
    async def test_middleware(self) -> None:
        """Test middleware processing."""
        bus = EventBus()
        received = []
        
        async def add_timestamp(event: Event) -> Event:
            event.data["processed"] = True
            return event
        
        bus.use(add_timestamp)
        
        @bus.on("test.event")
        def handler(event: Event) -> None:
            received.append(event.data.get("processed"))
        
        await bus.emit(Event(type="test.event"))
        
        assert received[0] is True


class TestStateManager:
    """Tests for StateManager."""

    @pytest.mark.asyncio
    async def test_set_and_get(self) -> None:
        """Test basic set and get operations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state = StateManager(FileStateBackend(tmpdir))
            
            await state.set("key1", {"data": "value"})
            result = await state.get("key1")
            
            assert result == {"data": "value"}

    @pytest.mark.asyncio
    async def test_get_default(self) -> None:
        """Test get with default value."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state = StateManager(FileStateBackend(tmpdir))
            
            result = await state.get("nonexistent", default="default")
            
            assert result == "default"

    @pytest.mark.asyncio
    async def test_update_versioning(self) -> None:
        """Test optimistic locking with versions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state = StateManager(FileStateBackend(tmpdir))
            
            # Set initial value
            await state.set("key", "value1")
            obj = await state.get_state_obj("key")
            assert obj.version == 1
            
            # Update with correct version
            success = await state.update("key", "value2", version=1)
            assert success
            
            obj = await state.get_state_obj("key")
            assert obj.version == 2
            assert obj.value == "value2"
            
            # Update with wrong version should fail
            success = await state.update("key", "value3", version=1)
            assert not success

    @pytest.mark.asyncio
    async def test_delete(self) -> None:
        """Test state deletion."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state = StateManager(FileStateBackend(tmpdir))
            
            await state.set("key", "value")
            assert await state.exists("key")
            
            deleted = await state.delete("key")
            assert deleted
            assert not await state.exists("key")

    @pytest.mark.asyncio
    async def test_increment(self) -> None:
        """Test atomic increment."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state = StateManager(FileStateBackend(tmpdir))
            
            val1 = await state.increment("counter")
            val2 = await state.increment("counter", 5)
            val3 = await state.increment("counter")
            
            assert val1 == 1
            assert val2 == 6
            assert val3 == 7

    @pytest.mark.asyncio
    async def test_list_keys(self) -> None:
        """Test listing state keys."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state = StateManager(FileStateBackend(tmpdir))
            
            await state.set("prefix:key1", "value1")
            await state.set("prefix:key2", "value2")
            await state.set("other:key3", "value3")
            
            all_keys = await state.list()
            assert len(all_keys) == 3
            
            prefix_keys = await state.list("prefix:")
            assert len(prefix_keys) == 2

    @pytest.mark.asyncio
    async def test_clear(self) -> None:
        """Test clearing all state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state = StateManager(FileStateBackend(tmpdir))
            
            await state.set("key1", "value1")
            await state.set("key2", "value2")
            
            count = await state.clear()
            
            assert count == 2
            assert not await state.exists("key1")
            assert not await state.exists("key2")


class TestTimerSource:
    """Tests for TimerSource."""

    @pytest.mark.asyncio
    async def test_scheduled_event(self) -> None:
        """Test scheduled recurring events."""
        bus = EventBus()
        received = []
        
        @bus.on("timer.tick")
        def handler(event: Event) -> None:
            received.append(event.timestamp)
        
        timer = TimerSource(bus)
        await timer.start()
        
        # Schedule event every 0.1 seconds
        timer.schedule("timer.tick", interval=0.1)
        
        # Wait for a few events
        await asyncio.sleep(0.35)
        await timer.stop()
        
        # Should have received at least 2 events
        assert len(received) >= 2

    @pytest.mark.asyncio
    async def test_cancel_schedule(self) -> None:
        """Test cancelling a scheduled event."""
        bus = EventBus()
        received = []
        
        @bus.on("timer.tick")
        def handler(event: Event) -> None:
            received.append(event)
        
        timer = TimerSource(bus)
        await timer.start()
        
        timer.schedule("timer.tick", interval=0.1)
        await asyncio.sleep(0.15)
        
        # Cancel the schedule
        cancelled = timer.cancel("timer.tick")
        assert cancelled
        
        count_before = len(received)
        await asyncio.sleep(0.2)
        
        # Should not have received more events
        assert len(received) == count_before


class TestIntegration:
    """Integration tests."""

    @pytest.mark.asyncio
    async def test_event_driven_workflow(self) -> None:
        """Test a complete event-driven agent workflow."""
        bus = EventBus()
        
        workflow_steps = []
        
        @bus.on("workflow.step1.complete")
        async def step2(event: Event) -> None:
            workflow_steps.append("step2")
            await bus.emit(Event(
                type="workflow.step2.complete",
                data={"result": event.data["input"] + "_processed"}
            ))
        
        @bus.on("workflow.step2.complete")
        async def step3(event: Event) -> None:
            workflow_steps.append("step3")
        
        # Start workflow
        await bus.emit(Event(
            type="workflow.step1.complete",
            data={"input": "test_data"}
        ))
        
        # Give async handlers time to complete
        await asyncio.sleep(0.1)
        
        assert "step2" in workflow_steps
        assert "step3" in workflow_steps

    @pytest.mark.asyncio
    async def test_state_with_events(self) -> None:
        """Test state management with event triggers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bus = EventBus()
            state = StateManager(FileStateBackend(tmpdir))
            
            @bus.on("user.action")
            async def handle_action(event: Event) -> None:
                user_id = event.data["user_id"]
                action = event.data["action"]
                
                # Update user state
                current = await state.get(f"user:{user_id}", {"actions": []})
                current["actions"].append(action)
                await state.set(f"user:{user_id}", current)
            
            # Simulate user actions
            await bus.emit(Event(type="user.action", data={
                "user_id": "user123",
                "action": "click"
            }))
            await bus.emit(Event(type="user.action", data={
                "user_id": "user123",
                "action": "scroll"
            }))
            
            # Give handler time
            await asyncio.sleep(0.1)
            
            # Verify state
            user_state = await state.get("user:user123")
            assert user_state["actions"] == ["click", "scroll"]
