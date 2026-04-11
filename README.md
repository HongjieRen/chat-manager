# chat-manager

A Claude Code skill for managing AI chat history across **Claude Code, Codex CLI, and multiple machines** — list, search, inspect, delete, and resume past sessions.

![demo](https://raw.githubusercontent.com/Scigentic-Labs/chat-manager/main/demo.gif)

A Claude Code skill for managing your conversation history — list, search, inspect, delete, and resume past sessions.

## Install

```bash
npx skills add Scigentic-Labs/chat-manager
```

## Usage

Invoke with `/chat-manager` in Claude Code.

| Command | Description |
|---------|-------------|
| *(default)* | List all conversations with project, date, message count, and size |
| `search <keyword>` | Full-text search across all records, returns matching snippets |
| `show <number>` | Inspect all user messages in a session |
| `resume <number>` | Get the `claude --resume <id>` command to re-enter a session |
| `delete <number(s)>` | Delete one or more sessions, e.g. `delete 1,3,5` |
| `cleanup` | Auto-scan for low-signal sessions and batch delete with confirmation |

## Cleanup criteria

The `cleanup` command flags sessions that match any of:
- 0–2 user messages (too short)
- Low-signal opener: `hey`, `hello`, `test`, system-only messages, JSON pings
- Duplicate topics (repeated identical first messages)

## Maintained by

[Scigentic Labs](https://github.com/Scigentic-Labs)
