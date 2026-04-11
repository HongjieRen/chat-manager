#!/usr/bin/env python3
"""chat-manager: multi-source AI chat history reader (Claude Code + Codex)"""

import argparse
import glob
import json
import os
import re
import shlex
import sys
from datetime import datetime

CONFIG_PATH = os.path.expanduser('~/.claude/chat-manager.config.json')


# ── Config ────────────────────────────────────────────────────────────────────

def load_config() -> list[dict]:
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            return json.load(f)['sources']
    return [{'type': 'claude-code', 'path': '~/.claude/projects/', 'machine': 'local'}]


# ── Claude Code adapter ───────────────────────────────────────────────────────

def claude_code_discover(source: dict) -> list[str]:
    base = os.path.expanduser(source['path'])
    if not os.path.isdir(base):
        print(f'[warn] source path not found: {base}', file=sys.stderr)
        return []
    return [p for p in glob.glob(f'{base}/**/*.jsonl', recursive=True)
            if '/subagents/' not in p]


def _extract_cwd(lines: list[str]) -> str:
    """Return the first non-empty cwd field found across all lines."""
    for line in lines:
        try:
            data = json.loads(line)
            cwd = data.get('cwd', '')
            if cwd:
                return cwd
        except Exception:
            continue
    return ''


def _project_name_from_dir(project_dir: str) -> str:
    """Decode Claude Code's URL-encoded project directory name."""
    name = project_dir.replace('-', '/')
    if name.startswith('/Users/'):
        parts = name.split('/')
        name = '/'.join(p for p in parts[3:] if p) or '~'
    return name


def claude_code_parse(path: str, source: dict) -> dict | None:
    try:
        with open(path) as f:
            lines = f.readlines()

        base = os.path.expanduser(source['path'])
        rel_path = os.path.relpath(path, base)
        project_dir = os.path.dirname(rel_path)
        session_id = os.path.basename(path).replace('.jsonl', '')
        project_name = _project_name_from_dir(project_dir)
        original_cwd = _extract_cwd(lines)

        first_msg = ''
        date_str = ''
        msg_count = 0

        for line in lines:
            data = json.loads(line)
            if data.get('type') == 'user' and not data.get('isMeta') and not data.get('isSidechain'):
                content = data['message'].get('content', '')
                if isinstance(content, list):
                    texts = [c.get('text', '') for c in content
                             if c.get('type') == 'text']
                    content = ' '.join(texts)
                if isinstance(content, str):
                    if '<command-' in content or '<local-command-' in content:
                        continue
                    stripped = content.strip()
                    if not first_msg and len(stripped) > 2:
                        first_msg = stripped.replace('\n', ' ')[:60]
                        date_str = data.get('timestamp', '')[:16].replace('T', ' ')
                msg_count += 1

        if not first_msg:
            first_msg = '(system/command only)'
        if not date_str:
            mtime = os.path.getmtime(path)
            date_str = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M')

        size_bytes = os.path.getsize(path)
        return {
            'source_type': 'claude-code',
            'machine':     source.get('machine', 'local'),
            'project':     project_name,
            'date':        date_str,
            'first_msg':   first_msg,
            'msgs':        msg_count,
            'size_bytes':  size_bytes,
            'size':        _human_size(size_bytes),
            'session_id':  session_id,
            'original_cwd': original_cwd,
            'path':        path,
        }
    except Exception:
        return None


# ── Codex adapter ─────────────────────────────────────────────────────────────

def codex_discover(source: dict) -> list[str]:
    """Return only main CLI sessions, filtering out subagent sessions."""
    base = os.path.expanduser(source['path'])
    if not os.path.isdir(base):
        print(f'[warn] source path not found: {base}', file=sys.stderr)
        return []
    paths = glob.glob(f'{base}/**/rollout-*.jsonl', recursive=True)
    result = []
    for p in paths:
        try:
            with open(p) as f:
                first_line = f.readline()
            first = json.loads(first_line)
            if (first.get('type') == 'session_meta' and
                    isinstance(first.get('payload', {}).get('source'), str) and
                    first['payload']['source'] == 'cli'):
                result.append(p)
        except Exception:
            pass
    return result


def _is_terminal_prompt(message: str) -> bool:
    """Detect shell prompt lines like 'kevinren@192 ~ %'."""
    parts = message.split()
    if parts and '@' in parts[0]:
        return True
    return False


def codex_parse(path: str, source: dict) -> dict | None:
    try:
        with open(path) as f:
            lines = f.readlines()

        if not lines:
            return None

        meta = json.loads(lines[0])
        payload = meta.get('payload', {})
        session_id = payload.get('id', os.path.basename(path).replace('.jsonl', ''))
        original_cwd = payload.get('cwd', '')
        ts = payload.get('timestamp', '')
        date_str = ts[:16].replace('T', ' ') if ts else ''

        if original_cwd:
            home = os.path.expanduser('~')
            if original_cwd == home:
                project_name = '~'
            else:
                project_name = os.path.basename(original_cwd.rstrip('/'))
        else:
            project_name = '(unknown)'

        first_msg = ''
        msg_count = 0

        for line in lines[1:]:
            try:
                event = json.loads(line)
            except Exception:
                continue
            if event.get('type') != 'event_msg':
                continue
            ep = event.get('payload', {})
            if ep.get('type') != 'user_message':
                continue
            message = ep.get('message', '')
            if _is_terminal_prompt(message):
                continue
            msg_count += 1
            if not first_msg and message.strip():
                first_msg = message.strip().replace('\n', ' ')[:60]

        if not first_msg:
            first_msg = '(no user messages)'
        if not date_str:
            mtime = os.path.getmtime(path)
            date_str = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M')

        size_bytes = os.path.getsize(path)
        return {
            'source_type':  'codex',
            'machine':      source.get('machine', 'local'),
            'project':      project_name,
            'date':         date_str,
            'first_msg':    first_msg,
            'msgs':         msg_count,
            'size_bytes':   size_bytes,
            'size':         _human_size(size_bytes),
            'session_id':   session_id,
            'original_cwd': original_cwd,
            'path':         path,
        }
    except Exception:
        return None


# ── Adapter registry ──────────────────────────────────────────────────────────

ADAPTERS = {
    'claude-code': (claude_code_discover, claude_code_parse),
    'codex':       (codex_discover,       codex_parse),
    # 'gemini':    pending — ~/.gemini/history/ has no sessions yet
}


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _human_size(size_bytes: int) -> str:
    if size_bytes > 1_048_576:
        return f'{size_bytes / 1_048_576:.1f}MB'
    elif size_bytes > 1024:
        return f'{size_bytes / 1024:.1f}KB'
    return f'{size_bytes}B'


def _gather_records(config: list[dict]) -> list[dict]:
    records = []
    for source in config:
        adapter_type = source.get('type')
        if adapter_type not in ADAPTERS:
            print(f'[warn] unknown source type: {adapter_type}', file=sys.stderr)
            continue
        discover_fn, parse_fn = ADAPTERS[adapter_type]
        for path in discover_fn(source):
            rec = parse_fn(path, source)
            if rec:
                records.append(rec)
    records.sort(key=lambda r: r['date'], reverse=True)
    return records


# ── Inspect helpers ───────────────────────────────────────────────────────────

def _summarize_input(inp: dict) -> str:
    """Compact single-line summary of a tool input dict."""
    if not inp:
        return ''
    # Common tool-specific extractions
    if 'command' in inp:
        return inp['command'][:60].replace('\n', ' ')
    if 'file_path' in inp:
        return os.path.basename(inp['file_path'])
    if 'pattern' in inp:
        return inp['pattern'][:60]
    if 'path' in inp:
        return os.path.basename(inp['path'])
    # Generic: first 2 key=value pairs
    pairs = [f'{k}={str(v)[:30]}' for k, v in list(inp.items())[:2]]
    return ', '.join(pairs)[:60]


def _render_claude_blocks(data: dict) -> list[str]:
    """Extract printable lines from a Claude Code JSONL message row."""
    message = data.get('message', {})
    content = message.get('content', '')
    out = []

    if isinstance(content, str):
        stripped = content.strip()
        if stripped:
            out.append(stripped)
        return out

    if not isinstance(content, list):
        return out

    for block in content:
        bt = block.get('type', '')
        if bt == 'text':
            text = block.get('text', '').strip()
            if text:
                out.append(text)
        elif bt == 'tool_use':
            name = block.get('name', '?')
            summary = _summarize_input(block.get('input', {}))
            out.append(f'→ {name}({summary})')
        elif bt == 'tool_result':
            body = block.get('content', '')
            if isinstance(body, list):
                texts = [b.get('text', '') for b in body
                         if isinstance(b, dict) and b.get('type') == 'text']
                body = '\n'.join(texts)
            snippet = str(body)[:200].replace('\n', ' ')
            prefix = '✗' if block.get('is_error') else '←'
            if snippet:
                out.append(f'{prefix} {snippet}')
        # thinking: hidden by default (no --show-thinking flag yet)
    return out


def _render_codex_items(lines: list[str]) -> list[tuple[str, str, str]]:
    """
    Parse Codex JSONL response_item stream.
    Returns list of (role_label, body, timestamp).
    role_label: 'USER' | 'ASST' | 'TOOL'
    """
    items = []
    for line in lines:
        try:
            event = json.loads(line)
        except Exception:
            continue
        if event.get('type') != 'response_item':
            continue
        payload = event.get('payload', {})
        pt = payload.get('type', '')
        ts = event.get('timestamp', '')[:16].replace('T', ' ')

        if pt == 'message':
            role = payload.get('role', '')
            if role == 'developer':
                continue  # system prompt — skip
            content = payload.get('content', [])
            texts = []
            for block in content:
                bt = block.get('type', '')
                if bt in ('input_text', 'output_text'):
                    texts.append(block.get('text', ''))
            body = '\n'.join(t for t in texts if t.strip())
            if not body:
                continue
            if role == 'user' and _is_terminal_prompt(body):
                continue
            role_label = 'USER' if role == 'user' else 'ASST'
            items.append((role_label, body, ts))

        elif pt == 'function_call':
            name = payload.get('name', '?')
            args_str = payload.get('arguments', '{}')
            try:
                args = json.loads(args_str)
            except Exception:
                args = {}
            summary = _summarize_input(args)
            items.append(('TOOL', f'→ {name}({summary})', ts))

        elif pt == 'function_call_output':
            out = payload.get('output', '')
            if isinstance(out, dict):
                out = out.get('content', '') or json.dumps(out)[:200]
            snippet = str(out)[:200].replace('\n', ' ')
            items.append(('TOOL', f'← {snippet}', ts))

    return items


# ── Searchable text extraction ─────────────────────────────────────────────────

def _extract_searchable_text(path: str, source_type: str) -> list[tuple[str, str, str]]:
    """
    Return (role, text, timestamp) chunks from a session file.
    Text is human-readable (no raw JSON structures).
    Used by both search and cleanup/_dupe_key.
    """
    try:
        with open(path) as f:
            lines = f.readlines()
    except Exception:
        return []

    chunks = []

    if source_type == 'claude-code':
        for line in lines:
            try:
                data = json.loads(line)
            except Exception:
                continue
            if data.get('isSidechain'):
                continue
            role_type = data.get('type', '')
            if role_type not in ('user', 'assistant'):
                continue
            ts = data.get('timestamp', '')[:16].replace('T', ' ')
            role_label = 'USER' if role_type == 'user' else 'ASST'
            rendered = _render_claude_blocks(data)
            for text in rendered:
                if text.strip():
                    chunks.append((role_label, text, ts))

    elif source_type == 'codex':
        chunks = _render_codex_items(lines)

    return chunks


# ── Cleanup helpers ────────────────────────────────────────────────────────────

def _dupe_key(record: dict, path: str) -> str | None:
    """
    Derive a deduplication key from the first 3 substantive user messages.
    Returns None if the session should be excluded from dupe grouping
    (e.g., agent subagent files, sessions with no real user content).
    """
    # Skip subagent files
    basename = os.path.basename(path)
    if basename.startswith('agent-'):
        return None

    chunks = _extract_searchable_text(path, record['source_type'])
    user_texts = []
    for role, text, _ in chunks:
        if role != 'USER':
            continue
        stripped = text.strip()
        # Skip XML-wrapped template blocks
        if stripped.startswith('<') and '>' in stripped[:40]:
            continue
        # Skip tool result lines from search (they start with ← or ✗)
        if stripped.startswith(('←', '✗')):
            continue
        # Skip terminal prompts (Codex side)
        if _is_terminal_prompt(stripped):
            continue
        user_texts.append(stripped[:120])
        if len(user_texts) >= 3:
            break

    if not user_texts:
        return None

    # Normalize: lowercase + collapse whitespace
    norm = ' | '.join(re.sub(r'\s+', ' ', t.lower()) for t in user_texts)
    return norm


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_scan(config: list[dict], as_json: bool = False) -> None:
    records = _gather_records(config)
    multi_source = len(config) > 1

    print(f'Found {len(records)} conversation(s):\n')

    if multi_source:
        print('| # | Machine | Source | Project | Date | First Message | Msgs | Size |')
        print('|---|---------|--------|---------|------|---------------|------|------|')
        for i, r in enumerate(records, 1):
            print(f'| {i} | {r["machine"]} | {r["source_type"]} | {r["project"]} '
                  f'| {r["date"]} | {r["first_msg"]} | {r["msgs"]} | {r["size"]} |')
    else:
        print('| # | Project | Date | First Message | Msgs | Size |')
        print('|---|---------|------|---------------|------|------|')
        for i, r in enumerate(records, 1):
            print(f'| {i} | {r["project"]} | {r["date"]} | {r["first_msg"]} '
                  f'| {r["msgs"]} | {r["size"]} |')

    print()
    print('Actions:')
    print('- To inspect: inspect <path>')
    print('- To resume:  resume <path>')
    print('- To search:  search <keyword>')
    print('- To cleanup: cleanup')

    if as_json:
        # Write JSON row→path map to stderr to keep stdout clean
        row_map = {i: r['path'] for i, r in enumerate(records, 1)}
        print(json.dumps(row_map, indent=2), file=sys.stderr)


def cmd_search(config: list[dict], keyword: str) -> None:
    records = _gather_records(config)
    results = []
    kw_lower = keyword.lower()
    multi_source = len(config) > 1

    for r in records:
        chunks = _extract_searchable_text(r['path'], r['source_type'])
        for role, text, ts in chunks:
            if kw_lower not in text.lower():
                continue
            idx = text.lower().find(kw_lower)
            snippet = text[max(0, idx - 60):idx + 120].replace('\n', ' ')
            results.append({**r, 'match_role': role, 'snippet': snippet, 'match_ts': ts})
            break  # one match per session

    if not results:
        print(f'No results found for: {keyword}')
        return

    print(f'Found {len(results)} match(es) for "{keyword}":\n')
    for i, r in enumerate(results, 1):
        machine_info = f' / {r["machine"]}' if multi_source else ''
        print(f'{i}. [{r["project"]}{machine_info}] {r["date"]}  ({r["match_role"]})')
        print(f'   ...{r["snippet"]}...')
        print(f'   Path: {r["path"]}')
        print()


def cmd_inspect(config: list[dict], path: str) -> None:
    path = os.path.expanduser(path)
    if not os.path.isfile(path):
        print(f'File not found: {path}', file=sys.stderr)
        sys.exit(1)

    source_type = 'codex' if 'rollout-' in os.path.basename(path) else 'claude-code'
    print(f'Session: {path}\n')

    try:
        with open(path) as f:
            lines = f.readlines()

        msg_num = 0

        if source_type == 'claude-code':
            for line in lines:
                try:
                    data = json.loads(line)
                except Exception:
                    continue
                if data.get('isSidechain'):
                    continue
                if data.get('isMeta'):
                    continue
                role_type = data.get('type', '')
                if role_type not in ('user', 'assistant'):
                    continue

                rendered = _render_claude_blocks(data)
                if not rendered:
                    continue

                # Skip user messages that are purely command wrappers
                if role_type == 'user':
                    content = data.get('message', {}).get('content', '')
                    if isinstance(content, str) and (
                            '<command-' in content or '<local-command-' in content):
                        continue

                ts = data.get('timestamp', '')[:16].replace('T', ' ')
                role_label = 'USER' if role_type == 'user' else 'ASST'
                msg_num += 1
                print(f'[{msg_num}] {role_label}  {ts}')
                for text in rendered:
                    print(text)
                print()

        else:  # codex
            items = _render_codex_items(lines)
            for role_label, body, ts in items:
                msg_num += 1
                print(f'[{msg_num}] {role_label}  {ts}')
                print(body)
                print()

    except Exception as e:
        print(f'Error reading file: {e}', file=sys.stderr)
        sys.exit(1)


def cmd_cleanup(config: list[dict]) -> None:
    records = _gather_records(config)
    candidates = []
    seen_keys: dict[str, str] = {}

    LOW_SIGNAL = {
        'hello', 'hey', 'hi', 'test', 'config', 'login',
        '收到', '你好', '(system/command only)', '(no user messages)',
    }

    for r in records:
        reasons = []

        # Rule 1: very short sessions
        if r['msgs'] <= 2:
            reasons.append('0–2 user messages')

        # Rule 2: low-signal opening message
        fm_lower = r['first_msg'].lower().strip()
        if fm_lower in LOW_SIGNAL:
            reasons.append('low-signal first message')

        # Rule 3: duplicate topic (conservative — needs 3-message key match)
        key = _dupe_key(r, r['path'])
        if key is not None:
            if key in seen_keys:
                reasons.append(
                    f'duplicate topic (first seen: {os.path.basename(seen_keys[key])})'
                )
            else:
                seen_keys[key] = r['path']

        if reasons:
            candidates.append({**r, 'reasons': reasons})

    if not candidates:
        print('No cleanup candidates found.')
        return

    print(f'Found {len(candidates)} cleanup candidate(s):\n')
    print('| # | Project | Date | Msgs | Size | Reasons |')
    print('|---|---------|------|------|------|---------|')
    for i, r in enumerate(candidates, 1):
        print(f'| {i} | {r["project"]} | {r["date"]} | {r["msgs"]} '
              f'| {r["size"]} | {"; ".join(r["reasons"])} |')
    print()
    print('To delete, confirm with the assistant and use: rm "<path>"')
    for i, r in enumerate(candidates, 1):
        print(f'{i}: {r["path"]}')


def cmd_resume(config: list[dict], path: str) -> None:
    path = os.path.expanduser(path)
    if not os.path.isfile(path):
        print(f'File not found: {path}', file=sys.stderr)
        sys.exit(1)

    rec = None
    for source in config:
        adapter_type = source.get('type')
        if adapter_type not in ADAPTERS:
            continue
        _, parse_fn = ADAPTERS[adapter_type]
        r = parse_fn(path, source)
        if r:
            rec = r
            break

    if not rec:
        print(f'Could not parse session: {path}', file=sys.stderr)
        sys.exit(1)

    cwd = rec['original_cwd'] or '~'
    cwd_quoted = shlex.quote(cwd)
    sid = rec['session_id']
    machine = rec['machine']
    source_type = rec['source_type']

    if source_type == 'claude-code':
        cmd = f'cd {cwd_quoted} && claude --resume {sid}'
        if machine == 'local':
            print(f'To continue this session, run in a new terminal:\n\n  {cmd}\n')
        else:
            print(f'This session is from {machine}, original path: {cwd}\n')
            print(f'On {machine}, run:\n  {cmd}\n')
            print(f'Or via SSH:\n  ssh {machine} \'{cmd}\'\n')

    elif source_type == 'codex':
        cmd = f'cd {cwd_quoted} && codex --resume {sid}'
        print(f'Codex session, run:\n\n  {cmd}\n')
        print('(Codex and Claude Code sessions cannot resume each other)')


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description='Multi-source AI chat history reader'
    )
    sub = parser.add_subparsers(dest='cmd', required=True)

    p_scan = sub.add_parser('scan', help='List all sessions in a table')
    p_scan.add_argument('--json', action='store_true', dest='as_json',
                        help='Also output JSON row→path map (written to stderr)')

    p_search = sub.add_parser('search', help='Full-text search across all sessions')
    p_search.add_argument('keyword', help='Search term')

    p_inspect = sub.add_parser('inspect', help='Print all messages in a session')
    p_inspect.add_argument('path', help='Absolute path to .jsonl file')

    sub.add_parser('cleanup', help='List cleanup candidates')

    p_resume = sub.add_parser('resume', help='Print resume command for a session')
    p_resume.add_argument('path', help='Absolute path to .jsonl file')

    args = parser.parse_args()
    config = load_config()

    if args.cmd == 'scan':
        cmd_scan(config, as_json=args.as_json)
    elif args.cmd == 'search':
        cmd_search(config, args.keyword)
    elif args.cmd == 'inspect':
        cmd_inspect(config, args.path)
    elif args.cmd == 'cleanup':
        cmd_cleanup(config)
    elif args.cmd == 'resume':
        cmd_resume(config, args.path)


if __name__ == '__main__':
    main()
