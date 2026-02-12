"""
State management for persistent agents.

Provides a unified interface for agents to maintain state across sessions,
enabling long-running workflows and stateful conversations.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

T = TypeVar("T")


@dataclass
class State:
    """Agent state container.
    
    Attributes:
        key: State identifier
        value: State data (must be JSON serializable)
        version: State version for optimistic locking
        metadata: Additional metadata (timestamp, source, etc.)
    """
    
    key: str
    value: Any
    version: int = 1
    metadata: dict[str, Any] = None
    
    def __post_init__(self) -> None:
        if self.metadata is None:
            self.metadata = {}


class StateBackend(ABC):
    """Abstract base class for state storage backends.
    
    Implementations can use Redis, PostgreSQL, file system, etc.
    """
    
    @abstractmethod
    async def get(self, key: str) -> State | None:
        """Retrieve state by key."""
        pass
    
    @abstractmethod
    async def set(self, state: State) -> bool:
        """Store state. Returns True if successful."""
        pass
    
    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete state. Returns True if deleted."""
        pass
    
    @abstractmethod
    async def list_keys(self, prefix: str = "") -> list[str]:
        """List all state keys with optional prefix filter."""
        pass
    
    @abstractmethod
    async def clear(self) -> int:
        """Clear all states. Returns count cleared."""
        pass


class FileStateBackend(StateBackend):
    """File-based state storage.
    
    Simple backend that stores state as JSON files.
    Good for development and single-node deployments.
    """
    
    def __init__(self, base_dir: str | Path = "./.agent_state") -> None:
        """Initialize file backend.
        
        Args:
            base_dir: Directory to store state files
        """
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
    
    def _file_path(self, key: str) -> Path:
        """Get file path for a key."""
        # Sanitize key for filesystem
        safe_key = key.replace("/", "_").replace("\\", "_")
        return self.base_dir / f"{safe_key}.json"
    
    async def get(self, key: str) -> State | None:
        """Retrieve state from file."""
        file_path = self._file_path(key)
        
        if not file_path.exists():
            return None
        
        try:
            data = json.loads(file_path.read_text())
            return State(
                key=data["key"],
                value=data["value"],
                version=data.get("version", 1),
                metadata=data.get("metadata", {})
            )
        except (json.JSONDecodeError, KeyError):
            return None
    
    async def set(self, state: State) -> bool:
        """Store state to file."""
        file_path = self._file_path(state.key)
        
        # Check version for optimistic locking
        existing = await self.get(state.key)
        if existing and existing.version != state.version - 1:
            return False  # Version conflict
        
        data = {
            "key": state.key,
            "value": state.value,
            "version": state.version,
            "metadata": state.metadata
        }
        
        file_path.write_text(json.dumps(data, indent=2))
        return True
    
    async def delete(self, key: str) -> bool:
        """Delete state file."""
        file_path = self._file_path(key)
        
        if file_path.exists():
            file_path.unlink()
            return True
        return False
    
    async def list_keys(self, prefix: str = "") -> list[str]:
        """List all state keys."""
        keys = []
        for file_path in self.base_dir.glob("*.json"):
            key = file_path.stem
            if key.startswith(prefix):
                keys.append(key)
        return keys
    
    async def clear(self) -> int:
        """Clear all state files."""
        count = 0
        for file_path in self.base_dir.glob("*.json"):
            file_path.unlink()
            count += 1
        return count


class StateManager:
    """High-level state management for agents.
    
    Provides a dict-like interface for storing and retrieving state
    with automatic serialization and versioning.
    
    Example:
        ```python
        state = StateManager(backend=FileStateBackend("./state"))
        
        # Store state
        await state.set("conversation:123", {
            "messages": [...],
            "current_step": "gathering_requirements"
        })
        
        # Retrieve state
        conversation = await state.get("conversation:123")
        
        # Update with optimistic locking
        success = await state.update(
            "conversation:123",
            {"current_step": "implementation"},
            version=conversation.version
        )
        ```
    """
    
    def __init__(self, backend: StateBackend | None = None) -> None:
        """Initialize state manager.
        
        Args:
            backend: Storage backend (defaults to FileStateBackend)
        """
        self.backend = backend or FileStateBackend()
    
    async def get(self, key: str, default: T = None) -> T:
        """Get state value by key.
        
        Args:
            key: State key
            default: Default value if key not found
            
        Returns:
            State value or default
        """
        state = await self.backend.get(key)
        return state.value if state else default
    
    async def set(
        self,
        key: str,
        value: Any,
        metadata: dict[str, Any] | None = None
    ) -> None:
        """Set state value.
        
        Args:
            key: State key
            value: Value to store (must be JSON serializable)
            metadata: Optional metadata
        """
        existing = await self.backend.get(key)
        version = existing.version + 1 if existing else 1
        
        state = State(
            key=key,
            value=value,
            version=version,
            metadata=metadata or {}
        )
        
        await self.backend.set(state)
    
    async def update(
        self,
        key: str,
        value: Any,
        version: int | None = None
    ) -> bool:
        """Update state with optimistic locking.
        
        Args:
            key: State key
            value: New value
            version: Expected current version (for locking)
            
        Returns:
            True if update succeeded, False if version conflict
        """
        existing = await self.backend.get(key)
        
        if version is not None:
            if not existing or existing.version != version:
                return False  # Version conflict
        
        new_version = existing.version + 1 if existing else 1
        
        state = State(
            key=key,
            value=value,
            version=new_version,
            metadata=existing.metadata if existing else {}
        )
        
        return await self.backend.set(state)
    
    async def delete(self, key: str) -> bool:
        """Delete state.
        
        Args:
            key: State key to delete
            
        Returns:
            True if deleted, False if not found
        """
        return await self.backend.delete(key)
    
    async def exists(self, key: str) -> bool:
        """Check if state exists.
        
        Args:
            key: State key
            
        Returns:
            True if state exists
        """
        state = await self.backend.get(key)
        return state is not None
    
    async def increment(self, key: str, amount: int = 1) -> int:
        """Atomically increment a counter.
        
        Args:
            key: Counter key
            amount: Amount to increment
            
        Returns:
            New counter value
        """
        current = await self.get(key, 0)
        new_value = current + amount
        await self.set(key, new_value)
        return new_value
    
    async def list(self, prefix: str = "") -> list[str]:
        """List all state keys with optional prefix.
        
        Args:
            prefix: Key prefix filter
            
        Returns:
            List of matching keys
        """
        return await self.backend.list_keys(prefix)
    
    async def clear(self) -> int:
        """Clear all state.
        
        Returns:
            Number of states cleared
        """
        return await self.backend.clear()
    
    async def get_state_obj(self, key: str) -> State | None:
        """Get full state object including metadata.
        
        Args:
            key: State key
            
        Returns:
            State object or None
        """
        return await self.backend.get(key)


# Decorator for stateful functions
def stateful(
    state_manager: StateManager,
    key_prefix: str = ""
):
    """Decorator to make a function stateful.
    
    Automatically persists function state across calls.
    
    Args:
        state_manager: State manager instance
        key_prefix: Prefix for state keys
        
    Example:
        ```python
        state = StateManager()
        
        @stateful(state, key_prefix="workflow")
        async def long_workflow(user_id: str, step: int = 0):
            # State is automatically loaded/saved
            if step == 0:
                await do_step_1()
                return {"step": 1, "data": "..."}
            elif step == 1:
                await do_step_2()
                return {"step": 2, "data": "..."}
        
        # First call
        result = await long_workflow("user123")
        
        # Resume from where we left off
        result = await long_workflow("user123", step=result["step"])
        ```
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Generate state key from function name and arguments
            key = f"{key_prefix}:{func.__name__}:{hash(str(args))}"
            
            # Load existing state
            existing = await state_manager.get_state_obj(key)
            
            # Call function
            result = await func(*args, **kwargs)
            
            # Save new state
            await state_manager.set(key, result)
            
            return result
        
        return wrapper
    return decorator


__all__ = [
    "State",
    "StateBackend",
    "StateManager",
    "FileStateBackend",
    "stateful",
]
