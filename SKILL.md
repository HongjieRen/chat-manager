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
_CM="python3 ~/.claude/skills/chat-manager/chat_manager.py"
_LOCAL_VER=$($CM version 2>/dev/null || echo "unknown")
_SNOOZE_FILE=~/.claude/chat-manager.update-snoozed
_REMOTE_VER=""

# Skip if snoozed for this version
_SNOOZED=false
if [ -f "$_SNOOZE_FILE" ]; then
  _SNOOZED_VER=$(awk '{print $1}' "$_SNOOZE_FILE")
  _SNOOZE_TS=$(awk '{print $2}' "$_SNOOZE_FILE")
  _NOW=$(date +%s)
  _SNOOZE_EXPIRES=$(( _SNOOZE_TS + 86400 ))
  if [ "$_SNOOZED_VER" != "" ] && [ "$_NOW" -lt "$_SNOOZE_EXPIRES" ]; then
    _SNOOZED=true
  fi
fi

if [ "$_SNOOZED" = "false" ]; then
  _REMOTE_VER=$(curl -sf --max-time 3 \
    https://raw.githubusercontent.com/Scigentic-Labs/chat-manager/main/chat_manager.py \
    | grep '^__version__' | head -1 | cut -d'"' -f2 2>/dev/null || echo "")
fi

if [ -n "$_REMOTE_VER" ] && [ "$_REMOTE_VER" != "$_LOCAL_VER" ]; then
  echo "UPGRADE_AVAILABLE $_LOCAL_VER $_REMOTE_VER"
fi
```

**If `UPGRADE_AVAILABLE` is printed:**

Use AskUserQuestion:
- header: "Update available"
- question: "chat-manager **v{new}** is available (you're on v{old}). Update now?"
- options:
  - "Yes, update now" → run the inline upgrade below
  - "Remind me tomorrow" → write snooze: `echo "{new} $(date +%s)" > ~/.claude/chat-manager.update-snoozed`; tell user "Reminder set for tomorrow"; continue with original command
  - "Skip this version" → write `echo "{new} 9999999999" > ~/.claude/chat-manager.update-snoozed`; tell user "Will not remind again for this version"; continue
  - "Never check for updates" → `echo "disabled" > ~/.claude/chat-manager.update-snoozed`; tell user "Update checks disabled. Delete `~/.claude/chat-manager.update-snoozed` to re-enable."; continue

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
