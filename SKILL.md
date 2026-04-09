---
name: chat-manager
description: List, inspect, search, and delete Claude Code chat history records across all projects
user_invocable: true
---

# Chat Manager

Manage Claude Code conversation history stored in `~/.claude/projects/`.

## How it works

Chat records are `.jsonl` files under `~/.claude/projects/<project-dir>/`. Each file is one conversation session.

## Instructions

When the user invokes `/chat-manager`, run the following Python script via Bash to scan all chat records and display them in a table:

```bash
python3 -c "
import json, os, glob

base = os.path.expanduser('~/.claude/projects')
records = []

for jsonl in sorted(glob.glob(f'{base}/**/*.jsonl', recursive=True)):
    try:
        # Skip subagent internal conversations
        if '/subagents/' in jsonl:
            continue

        size = os.path.getsize(jsonl)
        rel_path = os.path.relpath(jsonl, base)
        project_dir = os.path.dirname(rel_path)
        session_id = os.path.basename(jsonl).replace('.jsonl', '')

        # Parse project name from directory encoding
        project_name = project_dir.replace('-', '/')
        if project_name.startswith('/Users/'):
            parts = project_name.split('/')
            project_name = '/'.join(p for p in parts[3:] if p) or '~'

        first_msg = ''
        date_str = ''
        msg_count = 0

        with open(jsonl) as f:
            lines = f.readlines()

        for line in lines:
            data = json.loads(line)
            if data.get('type') == 'user' and not data.get('isMeta'):
                msg_count += 1
                content = data['message'].get('content', '')
                if isinstance(content, list):
                    texts = [c.get('text','') for c in content if c.get('type') == 'text']
                    content = ' '.join(texts)
                if isinstance(content, str):
                    # Skip system output and commands
                    if '<command-' in content or '<local-command-' in content:
                        continue
                    stripped = content.strip()
                    if not first_msg and len(stripped) > 2:
                        first_msg = stripped.replace('\n', ' ')[:60]
                        date_str = data.get('timestamp', '')[:16].replace('T', ' ')

        if not first_msg:
            first_msg = '(system/command only)'
        if not date_str:
            # Fallback to file mtime
            mtime = os.path.getmtime(jsonl)
            from datetime import datetime
            date_str = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M')

        if size > 1048576:
            size_str = f'{size/1048576:.1f}MB'
        elif size > 1024:
            size_str = f'{size/1024:.1f}KB'
        else:
            size_str = f'{size}B'

        records.append({
            'project': project_name,
            'date': date_str,
            'first_msg': first_msg,
            'msgs': msg_count,
            'size': size_str,
            'path': jsonl,
            'session_id': session_id
        })
    except Exception:
        pass

records.sort(key=lambda r: r['date'], reverse=True)

print(f'Found {len(records)} conversation(s):\n')
print('| # | Project | Date | First Message | Msgs | Size |')
print('|---|---------|------|---------------|------|------|')
for i, r in enumerate(records, 1):
    print(f'| {i} | {r[\"project\"]} | {r[\"date\"]} | {r[\"first_msg\"]} | {r[\"msgs\"]} | {r[\"size\"]} |')

print()
print('Actions:')
print('- To delete: tell me the row number(s), e.g. \"delete 1,3,5\"')
print('- To inspect: tell me the row number, e.g. \"show 2\"')
print('- To search: tell me a keyword, e.g. \"search gui-proxy\"')
print('- To resume: tell me the row number, e.g. \"resume 3\"')
print('- To auto-cleanup: say \"cleanup\"')
"
```

After displaying the table, wait for the user's instructions.

## Delete records

When the user asks to delete specific rows:

1. Confirm which records will be deleted (show project + first message)
2. After user confirms, delete the corresponding `.jsonl` files using `rm`
3. Re-run the scan to show the updated table

## Inspect a record

When the user asks to inspect/show a record, extract and display all user messages from that `.jsonl` file with timestamps.

## Search across records

When the user says `search <keyword>`, run this script to search across ALL `.jsonl` content (including subagents):

```bash
python3 -c "
import json, os, glob, sys

base = os.path.expanduser('~/.claude/projects')
keyword = 'KEYWORD_HERE'
results = []

for jsonl in sorted(glob.glob(f'{base}/**/*.jsonl', recursive=True)):
    try:
        session_id = os.path.basename(jsonl).replace('.jsonl', '')
        rel_path = os.path.relpath(jsonl, base)
        project_dir = os.path.dirname(rel_path)
        project_name = project_dir.replace('-', '/')
        if project_name.startswith('/Users/'):
            parts = project_name.split('/')
            project_name = '/'.join(p for p in parts[3:] if p) or '~'

        with open(jsonl) as f:
            content_full = f.read()

        if keyword.lower() not in content_full.lower():
            continue

        # Find context around match
        idx = content_full.lower().find(keyword.lower())
        snippet = content_full[max(0,idx-60):idx+120].replace('\n', ' ')

        # Get date from first line
        first_line = json.loads(content_full.split('\n')[0])
        date_str = first_line.get('timestamp', '')[:16].replace('T', ' ')

        results.append({
            'session_id': session_id,
            'project': project_name,
            'date': date_str,
            'snippet': snippet,
            'path': jsonl
        })
    except Exception:
        pass

if not results:
    print(f'No results found for: {keyword}')
else:
    print(f'Found {len(results)} match(es) for \"{keyword}\":\n')
    for i, r in enumerate(results, 1):
        print(f'{i}. [{r[\"project\"]}] {r[\"date\"]}')
        print(f'   Session: {r[\"session_id\"]}')
        print(f'   ...{r[\"snippet\"]}...')
        print(f'   Resume: claude --resume {r[\"session_id\"]}')
        print()
"
```

Replace `KEYWORD_HERE` with the actual search term. After showing results, offer to resume any of them.

## Resume a session

When the user says `resume <number>`, look up the session_id for that row and tell the user to run:

```
claude --resume <session-id>
```

Display this as a copyable command. Note that resuming requires running Claude Code fresh from the terminal — it cannot be done from within an active session.

## Suggest cleanup

When the user asks what can be cleaned up, or says `cleanup`, run the scan above then analyze each record and flag it as a cleanup candidate if it meets **any** of these criteria:

1. **0–2 user messages** — too short to have real value
2. **Low-signal first message** — matches patterns like: `hello`, `hey`, `test`, `config`, `login`, `what's your model`, `收到`, `你好` (greeting only), JSON ping payloads, or `(system/command only)`
3. **Duplicate topic** — multiple records with nearly identical first messages (e.g. repeated "收到请回复1" blasts)

Present candidates grouped by reason in a table. Always include the row number, message count, size, and reason. Ask the user to confirm before deleting — offer "delete all candidates" as a single confirm option.

## Important

- NEVER delete records without explicit user confirmation
- The current active session cannot be deleted (warn the user if they try)
- Always show the updated table after deletions
