# Kimi Agent SDK for Go

A Go SDK for interacting with the Kimi Agent CLI, enabling programmatic control of AI agent sessions through a wire protocol.

## Installation

```bash
go get github.com/MoonshotAI/kimi-agent-sdk/go
```

## Prerequisites

- Go 1.21 or later
- `kimi` CLI installed and available in your PATH
- `KIMI_API_KEY` environment variable set (or configured via config file)

## Quick Start

```go
package main

import (
    "context"
    "fmt"
    "time"

    kimi "github.com/MoonshotAI/kimi-agent-sdk/go"
    "github.com/MoonshotAI/kimi-agent-sdk/go/wire"
)

func main() {
    // Create a new session
    session, err := kimi.NewSession(
        kimi.WithAutoApprove(), // Auto-approve tool calls
    )
    if err != nil {
        panic(err)
    }
    defer session.Close()

    // Create a context with timeout
    ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
    defer cancel()

    // Send a message and get a turn
    turn, err := session.RoundTrip(ctx, wire.NewStringUserInput("Hello, Kimi!"))
    if err != nil {
        panic(err)
    }

    // Process steps and messages
    for step := range turn.Steps {
        for msg := range step.Messages {
            switch m := msg.(type) {
            case wire.ContentPart:
                if m.Type == wire.ContentPartTypeText {
                    fmt.Print(m.Text)
                }
            case wire.ToolCall:
                fmt.Printf("\n[Tool Call: %s]\n", m.Function.Name)
            case wire.ToolResult:
                fmt.Printf("[Tool Result: %s]\n", m.ToolCallID)
            }
        }
    }

    // Check the result
    result := turn.Result()
    fmt.Printf("\nStatus: %s\n", result.Status)

    // Get token usage
    usage := turn.Usage()
    fmt.Printf("Tokens - Input: %d, Output: %d\n",
        usage.Tokens.InputOther, usage.Tokens.Output)
}
```

## API Reference

### Session

#### `NewSession(options ...Option) (*Session, error)`

Creates a new Kimi agent session. The session spawns the `kimi` CLI process and communicates with it via JSON-RPC over stdin/stdout.

#### `(*Session) RoundTrip(ctx context.Context, content wire.Content) (*Turn, error)`

Sends user input and returns a Turn representing the agent's response. The Turn provides channels for streaming the response.

#### `(*Session) Close() error`

Closes the session and terminates the underlying CLI process.

### Turn

#### `(*Turn) Steps <-chan *Step`

A channel that yields Steps as the agent processes the request. Each Step contains a Messages channel.

#### `(*Turn) Result() wire.PromptResult`

Returns the final result status of the turn.

#### `(*Turn) Usage() *Usage`

Returns token usage statistics for the turn.

#### `(*Turn) Cancel() error`

Cancels the current turn and cleans up resources.

#### `(*Turn) Err() error`

Returns any background error that occurred during the turn.

### Options

| Option | Description |
|--------|-------------|
| `WithExecutable(path)` | Use a custom path to the kimi CLI binary |
| `WithConfig(config)` | Pass a Config struct as JSON |
| `WithConfigFile(path)` | Use a specific config file |
| `WithModel(model)` | Specify the model to use |
| `WithWorkDir(dir)` | Set the working directory for the agent |
| `WithSession(id)` | Resume an existing session |
| `WithMCPConfigFile(path)` | Use a specific MCP config file |
| `WithMCPConfig(config)` | Pass MCP configuration |
| `WithAutoApprove()` | Auto-approve all tool calls |
| `WithThinking(bool)` | Enable or disable thinking mode |
| `WithSkillsDir(dir)` | Set the skills directory |

### Message Types

The SDK provides various message types through the `wire` package:

| Type | Description |
|------|-------------|
| `ContentPart` | Text or thinking content from the agent |
| `ToolCall` | Agent requesting to call a tool |
| `ToolCallPart` | Streaming tool call arguments |
| `ToolResult` | Result from a tool execution |
| `ApprovalRequest` | Request for user approval (when auto-approve is disabled) |
| `StatusUpdate` | Token usage and context updates |
| `SubagentEvent` | Events from sub-agents |

### Handling Approval Requests

When `WithAutoApprove()` is not used, you need to handle approval requests:

```go
for step := range turn.Steps {
    for msg := range step.Messages {
        if req, ok := msg.(wire.ApprovalRequest); ok {
            fmt.Printf("Tool: %s\nAction: %s\nDescription: %s\n",
                req.Sender, req.Action, req.Description)

            // Approve the request
            req.Respond(wire.RequestResponseApprove)

            // Or reject it
            // req.Respond(wire.RequestResponseReject)

            // Or approve for the entire session
            // req.Respond(wire.RequestResponseApproveForSession)
        }
    }
}
```

## Configuration

### Config Struct

```go
config := &kimi.Config{
    DefaultModel: "moonshot-v1-8k",
    Models: map[string]kimi.LLMModel{
        "moonshot-v1-8k": {
            Provider:       "kimi",
            Model:          "moonshot-v1-8k",
            MaxContextSize: 8192,
        },
    },
    Providers: map[string]kimi.LLMProvider{
        "kimi": {
            Type:   kimi.ProviderTypeKimi,
            APIKey: "your-api-key",
        },
    },
    LoopControl: kimi.LoopControl{
        MaxStepsPerRun:    10,
        MaxRetriesPerStep: 3,
    },
}

session, err := kimi.NewSession(kimi.WithConfig(config))
```

### Supported Providers

- `kimi` - Moonshot AI (Kimi)
- `openai_legacy` - OpenAI (legacy API)
- `openai_responses` - OpenAI (responses API)
- `anthropic` - Anthropic (Claude)
- `gemini` / `google_genai` - Google Gemini
- `vertexai` - Google Vertex AI

## Important Notes

1. **Sequential RoundTrips**: The current implementation expects RoundTrips to be called sequentially. Start a new RoundTrip only after the previous one has completed (all Steps and Messages consumed).

2. **Context Cancellation**: Use context cancellation to abort long-running requests. The SDK will signal the CLI to cancel the operation.

3. **Resource Cleanup**: Always call `session.Close()` when done, preferably with `defer`. This ensures the CLI process is terminated properly.

4. **Error Handling**: Check `turn.Err()` after consuming all messages to detect any background errors that occurred during processing.

5. **Channel Consumption**: You must consume all messages from `step.Messages` before moving to the next step, and all steps from `turn.Steps` before calling `turn.Cancel()` or starting a new RoundTrip.

6. **Approval Handling**: When not using `WithAutoApprove()`, you must respond to approval requests, otherwise the agent will wait indefinitely.

## Running Tests

```bash
# Unit tests
go test ./...

# Integration tests (requires mock_kimi binary)
cd test/integration
go build -o testdata/mock_kimi testdata/mock_kimi.go
go test -v ./...

# E2E tests (requires KIMI_API_KEY)
KIMI_API_KEY=your-key go test -v ./test/e2e/...
```

## License

See the LICENSE file in the root of this repository.
