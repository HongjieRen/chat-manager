---
name: chat-manager
description: List, inspect, search, and delete AI chat history across tools and machines
user_invocable: true
---

# Chat Manager

Manage conversation history from Claude Code, Codex CLI, and other AI tools.
Reads sources from `~/.claude/chat-manager.config.json` (defaults to `~/.claude/projects/`).

All logic lives in `chat_manager.py`. Each command below is a thin wrapper.

## List all records

Run:
```bash
python3 ~/.claude/skills/chat-manager/chat_manager.py scan
```
Display the table, then wait for the user's instruction.

For a JSON row→path map alongside the table:
```bash
python3 ~/.claude/skills/chat-manager/chat_manager.py scan --json
```

## Search

```bash
python3 ~/.claude/skills/chat-manager/chat_manager.py search "KEYWORD"
```

## Inspect a record

Look up the row's `path` from the previous scan output, then:
```bash
python3 ~/.claude/skills/chat-manager/chat_manager.py inspect "<path>"
```

## Resume a session

```bash
python3 ~/.claude/skills/chat-manager/chat_manager.py resume "<path>"
```
Script prints the exact `cd ... && claude --resume ...` command (or Codex equivalent).
For records from other machines, it also prints the SSH variant.

## Delete records

Confirm with user first, then directly `rm "<path>"` (do NOT go through the script — safety check stays in the assistant layer). Re-run scan after.

## Cleanup candidates

```bash
python3 ~/.claude/skills/chat-manager/chat_manager.py cleanup
```
Present candidates grouped by reason. Always confirm before deleting.

## Important

- NEVER delete without explicit confirmation
- The current active session cannot be deleted
- Always show updated table after deletions
