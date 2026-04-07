# Transcript JSON Schema

Reference documentation for the JSON output produced by `cc_transcript_exporter.py`. This format is compatible with `cc_transcript_analyzer.py` and `cc_transcript_compactor.py`.

## Top-Level Structure

```json
{
  "session": { ... },
  "messages": [ ... ],
  "chunks": [],
  "processes": [ ... ],
  "metrics": { ... }
}
```

| Key | Type | Description |
|-----|------|-------------|
| `session` | object | Session metadata |
| `messages` | array | Parsed conversation messages (main session) |
| `chunks` | array | Always empty — chunks are not produced from JSONL |
| `processes` | array | Subagent sessions |
| `metrics` | object | Aggregate token/timing metrics |

## `session` Object

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Session UUID |
| `projectId` | string | Encoded project directory name |
| `projectPath` | string | Absolute path to the project |
| `createdAt` | string | ISO 8601 timestamp of session start |
| `firstMessage` | string | First user message text (up to 200 chars) |
| `messageTimestamp` | string | Same as createdAt |
| `hasSubagents` | boolean | Whether the session spawned subagents |
| `messageCount` | number | Number of messages in the main session |
| `isOngoing` | boolean | Always false for exported sessions |
| `gitBranch` | string | Git branch at session start |
| `slug` | string | Custom session title (if set) |

## Message Object

Each entry in `messages[]` and `processes[].messages[]`:

| Field | Type | Description |
|-------|------|-------------|
| `uuid` | string | Unique message identifier |
| `parentUuid` | string\|null | Parent message UUID (tree linkage) |
| `type` | string | `"user"`, `"assistant"`, or `"system"` |
| `timestamp` | string | ISO 8601 timestamp |
| `role` | string | Same as type for conversation messages |
| `content` | string\|array | Message content (see Content Blocks) |
| `cwd` | string | Working directory at time of message |
| `gitBranch` | string | Git branch at time of message |
| `isSidechain` | boolean | Whether this is a subagent message |
| `isMeta` | boolean | Whether this is a meta/system message |
| `userType` | string | `"external"` for user input |
| `isCompactSummary` | boolean | Whether this is a compaction summary |
| `toolCalls` | array | Structured tool call data (assistant messages) |
| `toolResults` | array | Structured tool result data (user messages) |

Optional fields (present when available):
| `usage` | object | Token usage for this API response |
| `model` | string | Model used for this response |
| `requestId` | string | API request identifier |
| `subtype` | string | System message subtype (e.g., `"turn_duration"`) |

## Content Blocks

When `content` is an array, each element is a content block:

### Text Block
```json
{ "type": "text", "text": "Hello, world!" }
```

### Thinking Block
```json
{ "type": "thinking", "thinking": "Let me consider...", "signature": "..." }
```

### Tool Use Block
```json
{
  "type": "tool_use",
  "id": "toolu_01...",
  "name": "Bash",
  "input": { "command": "ls" }
}
```

### Tool Result Block
```json
{
  "type": "tool_result",
  "tool_use_id": "toolu_01...",
  "content": "file1.txt\nfile2.txt",
  "is_error": false
}
```

## `toolCalls` Array (Assistant Messages)

```json
{
  "id": "toolu_01...",
  "name": "Bash",
  "input": { "command": "ls" },
  "isTask": false
}
```

## `toolResults` Array (User Messages)

```json
{
  "toolUseId": "toolu_01...",
  "content": "file1.txt\nfile2.txt",
  "isError": false
}
```

## `processes[]` (Subagents)

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Agent identifier (hex string) |
| `filePath` | string | Path to the subagent JSONL file |
| `messages` | array | Parsed messages (same format as main) |
| `startTime` | string | ISO 8601 timestamp |
| `endTime` | string | ISO 8601 timestamp |
| `durationMs` | number | Duration in milliseconds |
| `metrics` | object | Token metrics for this subagent |
| `isParallel` | boolean | Whether agent ran in parallel |
| `isOngoing` | boolean | Always false for completed agents |
| `description` | string | Agent type and description (from meta.json) |

## `metrics` Object

Aggregate metrics across main session and all subagents:

| Field | Type | Description |
|-------|------|-------------|
| `durationMs` | number | Wall-clock duration of main session |
| `totalTokens` | number | Sum of all token categories |
| `inputTokens` | number | Non-cached input tokens |
| `outputTokens` | number | Generated output tokens |
| `cacheReadTokens` | number | Tokens read from prompt cache |
| `cacheCreationTokens` | number | Tokens written to prompt cache |
| `messageCount` | number | Total messages (main + subagents) |
| `byModel` | object | Per-model token breakdown (see below) |

### `metrics.byModel`

Maps model source name to token metrics. Orchestrator messages use the bare model name; subagent messages use `"{model} (agents)"` with an `agentCount` field.

```json
{
  "claude-opus-4-6": {
    "inputTokens": 177,
    "outputTokens": 7364,
    "cacheReadTokens": 607635,
    "cacheCreationTokens": 74659,
    "totalTokens": 689835
  },
  "claude-opus-4-6 (agents)": {
    "inputTokens": 5716,
    "outputTokens": 59135,
    "cacheReadTokens": 4947744,
    "cacheCreationTokens": 296717,
    "totalTokens": 5309312,
    "agentCount": 5
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `inputTokens` | number | Non-cached input tokens for this model |
| `outputTokens` | number | Generated output tokens for this model |
| `cacheReadTokens` | number | Tokens read from prompt cache |
| `cacheCreationTokens` | number | Tokens written to prompt cache |
| `totalTokens` | number | Sum of all token categories |
| `agentCount` | number | *(agents only)* Number of subagents using this model |

## `usage` Object (Per-Message)

Present on assistant messages:

```json
{
  "input_tokens": 3,
  "output_tokens": 150,
  "cache_read_input_tokens": 50000,
  "cache_creation_input_tokens": 12000,
  "service_tier": "standard"
}
```
