# Changelog


## Unreleased

### Added
- **New module: `kimi_agent_sdk.connectors`** - Agent connectivity framework
  - `EventBus`: Event-driven architecture for reactive agents
    * Subscribe with exact matching or wildcard patterns
    * Async/sync handler support
    * Middleware chain for event processing
    * Event history for debugging
  - `StateManager`: Persistent state management for stateful agents
    * Automatic versioning with optimistic locking
    * Pluggable backends (FileSystem included)
    * Atomic operations (increment, etc.)
  - `TimerSource`: Scheduled event emission for cron-like workflows
  - Complete example: Event-driven GitHub Bot
    * Responds to webhooks (PR, issues)
    * Maintains conversation state
    * Demonstrates multi-event workflows
  - 22 comprehensive test cases

## 0.0.4 (2026-02-10)
- Dependencies: Update kimi-cli to version 1.10, kosong to version 0.42
- API: Re-export `TurnEnd`, `ShellDisplayBlock`, `TodoDisplayItem`, and `SystemPromptTemplateError`

## 0.0.3 (2026-01-21)
- Docs: expand Python SDK guides (QuickStart, Prompt/Session, tools)
- Examples: add Python examples to demonstrate SDK features
- Code: add module-level docstrings to public modules; re-export SDK tools
- Dependencies: Update kimi-cli to version 0.83

## 0.0.2 (2025-01-20)
- Align Python SDK path types with Kimi CLI signatures
- Normalize SDK exceptions and propagate exceptions from CLI/Kosong 

## 0.0.1 (2025-01-16)

- Initial release of the Python SDK.
