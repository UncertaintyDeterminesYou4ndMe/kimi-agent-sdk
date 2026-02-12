# Event-Driven Agent Example

This example demonstrates the **Agent Connectivity Framework** by building an event-driven GitHub Bot that responds to webhooks and maintains state across interactions.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    GitHub Webhooks                          │
│           (PR opened, Issue created, etc.)                  │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                    EventBus                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │ github.pr.* │  │ github.issue│  │ agent.pr.review_*   │ │
│  │  handlers   │  │   handlers  │  │    handlers         │ │
│  └─────────────┘  └─────────────┘  └─────────────────────┘ │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                   StateManager                              │
│              (Persistent PR/Issue State)                    │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                     Kimi Agent                              │
│              (Code Review, Analysis)                        │
└─────────────────────────────────────────────────────────────┘
```

## Key Concepts Demonstrated

### 1. Event-Driven Architecture

```python
@bus.on("github.pr.opened")
async def on_pr_opened(event: Event) -> None:
    # React to PR being opened
    await bus.emit(Event(type="agent.pr.review_requested", data={...}))
```

- **Decoupled**: Handlers don't know about each other
- **Reactive**: Agent responds to external events
- **Extensible**: Easy to add new event types and handlers

### 2. State Persistence

```python
# Store conversation context
await state.set(f"pr:{pr_id}", context.__dict__)

# Retrieve later
context_data = await state.get(f"pr:{pr_id}")
```

- **Stateful**: Agent remembers previous interactions
- **Resilient**: State survives restarts
- **Versioned**: Optimistic locking prevents conflicts

### 3. Event Patterns

- **Exact matching**: `@bus.on("github.pr.opened")`
- **Wildcards**: `@bus.on("github.pr.*")`
- **Multi-level**: `@bus.on("github.*.created")`

## Running the Example

### Option 1: Simulation Mode (No GitHub needed)

```bash
python github_bot.py --simulate
```

This simulates GitHub events to demonstrate the event flow without needing actual webhooks.

### Option 2: Webhook Server (Production)

```bash
# Set up GitHub token
export GITHUB_TOKEN=ghp_your_token

# Start webhook server
python github_bot.py --port 8080

# Configure GitHub webhook to point to:
# http://your-server:8080/webhook
```

## Real-World Use Cases

### Use Case 1: Smart Code Review Bot

```python
@bus.on("github.pr.opened")
async def auto_review(event: Event) -> None:
    pr = event.data
    
    # Skip if PR is from bot
    if pr['author'] == 'dependabot[bot]':
        return
    
    # Analyze code
    review = await agent.review(pr['diff'])
    
    # Auto-approve if only minor changes
    if review['quality_score'] >= 8 and not review['issues']:
        await github.approve_pr(pr['number'])
    else:
        await github.request_changes(pr['number'], review['comments'])
```

### Use Case 2: Multi-Agent Collaboration

```python
@bus.on("agent.pr.security_check")
async def security_agent(event: Event) -> None:
    """Specialized security agent."""
    issues = await check_security(event.data['diff'])
    
    if issues:
        await bus.emit(Event(type="agent.pr.block", data={
            "pr_id": event.data['pr_id'],
            "reason": "security_issues",
            "details": issues
        }))

@bus.on("agent.pr.review_requested")
async def coordinator(event: Event) -> None:
    """Route to specialized agents."""
    # Parallel reviews
    await asyncio.gather(
        bus.emit(Event(type="agent.pr.security_check", data=event.data)),
        bus.emit(Event(type="agent.pr.style_check", data=event.data)),
        bus.emit(Event(type="agent.pr.logic_check", data=event.data)),
    )
```

### Use Case 3: Stateful Customer Support

```python
@bus.on("support.ticket.created")
async def handle_ticket(event: Event) -> None:
    ticket_id = event.data['ticket_id']
    
    # Load conversation history
    history = await state.get(f"ticket:{ticket_id}", [])
    
    # Generate response with context
    response = await agent.respond(
        message=event.data['message'],
        context=history
    )
    
    # Update history
    history.append({
        "role": "agent",
        "message": response,
        "timestamp": datetime.now()
    })
    await state.set(f"ticket:{ticket_id}", history)
```

## Extending the Framework

### Adding New Event Sources

```python
class SlackEventSource(EventSource):
    async def start(self):
        # Connect to Slack RTM API
        self.client = SlackClient(token)
        
        @self.client.on_message
        def on_slack_message(msg):
            self.bus.emit(Event(
                type="slack.message.received",
                data={"text": msg.text, "user": msg.user}
            ))
```

### Custom State Backends

```python
class RedisStateBackend(StateBackend):
    """Production-grade state storage."""
    
    async def get(self, key: str) -> State | None:
        data = await self.redis.get(f"agent:state:{key}")
        return State.parse(data) if data else None
    
    async def set(self, state: State) -> bool:
        await self.redis.setex(
            f"agent:state:{state.key}",
            ttl=3600,
            value=state.serialize()
        )
        return True
```

## Benefits Over Traditional Approaches

| Aspect | Traditional | Event-Driven |
|--------|-------------|--------------|
| **Coupling** | Tight - direct function calls | Loose - events mediate |
| **Extensibility** | Hard to add new integrations | Easy - just add handlers |
| **State** | Often stateless | Stateful by design |
| **Testing** | Mock entire dependencies | Emit test events |
| **Scalability** | Synchronous bottlenecks | Async by default |

## Next Steps

1. **Add Real GitHub Integration**: Use PyGithub library
2. **Multi-Agent Setup**: Run multiple specialized agents
3. **Web Dashboard**: Visualize event flow and state
4. **Metrics**: Track event processing latency
