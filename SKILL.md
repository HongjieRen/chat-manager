---
name: chat-manager
description: List, inspect, search, and delete AI chat history across tools and machines
user_invocable: true
---

# Chat Manager

Manage conversation history from Claude Code, Codex CLI, and other AI tools.
Reads sources from `~/.claude/chat-manager.config.json` (defaults to `~/.claude/projects/`).

All logic lives in `chat_manager.py`. Each command below is a thin wrapper.

---

## Update Check (run first, every invocation)

```bash
_LOCAL_VER=$(python3 ~/.claude/skills/chat-manager/chat_manager.py version 2>/dev/null || echo "unknown")
_AUTO_FILE=$HOME/.claude/chat-manager.auto-update
_REMOTE_VER=""

# If auto-update enabled, skip the prompt and upgrade silently
if [ -f "$_AUTO_FILE" ] && [ "$(cat "$_AUTO_FILE")" = "true" ]; then
  _REMOTE_VER=$(curl -sf --max-time 3 \
    https://raw.githubusercontent.com/Scigentic-Labs/chat-manager/main/chat_manager.py \
    | grep '^__version__' | head -1 | cut -d'"' -f2 2>/dev/null || echo "")
  if [ -n "$_REMOTE_VER" ] && [ "$_REMOTE_VER" != "$_LOCAL_VER" ]; then
    echo "AUTO_UPGRADE $_LOCAL_VER $_REMOTE_VER"
  fi
else
  _REMOTE_VER=$(curl -sf --max-time 3 \
    https://raw.githubusercontent.com/Scigentic-Labs/chat-manager/main/chat_manager.py \
    | grep '^__version__' | head -1 | cut -d'"' -f2 2>/dev/null || echo "")
  if [ -n "$_REMOTE_VER" ] && [ "$_REMOTE_VER" != "$_LOCAL_VER" ]; then
    echo "UPGRADE_AVAILABLE $_LOCAL_VER $_REMOTE_VER"
  fi
fi
```

**If `AUTO_UPGRADE` is printed:** run the inline upgrade silently, then tell user "chat-manager updated v{old} → v{new} (auto-update is on)." and continue.

**If `UPGRADE_AVAILABLE` is printed:**

Use AskUserQuestion:
- header: "Update available"
- question: "chat-manager **v{new}** is available (you're on v{old})."
- options:
  - "Yes, update now" → run the inline upgrade below, then continue with original command
  - "Enable auto-update" → run the inline upgrade below, then write `echo "true" > ~/.claude/chat-manager.auto-update`; tell user "Updated to v{new}. Future updates will install automatically."; continue with original command

**Inline upgrade flow:**

```bash
# Download new version
_DEST=~/.dotfiles/claude-code/skills/chat-manager/chat_manager.py
# Fallback if dotfiles path not found
[ ! -f "$_DEST" ] && _DEST=~/.claude/skills/chat-manager/chat_manager.py

curl -sf --max-time 15 \
  https://raw.githubusercontent.com/Scigentic-Labs/chat-manager/main/chat_manager.py \
  -o "$_DEST" && echo "UPDATE_OK" || echo "UPDATE_FAILED"
```

- **UPDATE_OK:** clear snooze (`rm -f ~/.claude/chat-manager.update-snoozed`), tell user "Updated to v{new}!"; continue with original command
- **UPDATE_FAILED:** tell user "Update failed — still on v{old}. Try manually: `curl -sf https://raw.githubusercontent.com/Scigentic-Labs/chat-manager/main/chat_manager.py -o ~/.claude/skills/chat-manager/chat_manager.py`"; continue with original command

**If no `UPGRADE_AVAILABLE` output:** continue silently.

---

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
The JSON map is written to stderr — read it separately if needed.

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
