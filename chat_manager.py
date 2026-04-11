#!/usr/bin/env python3
"""chat-manager: multi-source AI chat history reader (Claude Code + Codex)"""

import argparse
import glob
import json
import os
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
            if data.get('type') == 'user' and not data.get('isMeta'):
                msg_count += 1
                content = data['message'].get('content', '')
                if isinstance(content, list):
                    texts = [c.get('text', '') for c in content if c.get('type') == 'text']
                    content = ' '.join(texts)
                if isinstance(content, str):
                    if '<command-' in content or '<local-command-' in content:
                        continue
                    stripped = content.strip()
                    if not first_msg and len(stripped) > 2:
                        first_msg = stripped.replace('\n', ' ')[:60]
                        date_str = data.get('timestamp', '')[:16].replace('T', ' ')

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

        # Project: last component of cwd, or '~' for home
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


def _find_record_by_path(path: str, config: list[dict]) -> dict | None:
    for source in config:
        adapter_type = source.get('type')
        if adapter_type not in ADAPTERS:
            continue
        _, parse_fn = ADAPTERS[adapter_type]
        rec = parse_fn(path, source)
        if rec:
            return rec
    return None


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
        row_map = {i: r['path'] for i, r in enumerate(records, 1)}
        print('\nJSON row→path map:')
        print(json.dumps(row_map, indent=2))


def cmd_search(config: list[dict], keyword: str) -> None:
    records = _gather_records(config)
    results = []

    for r in records:
        try:
            with open(r['path']) as f:
                content = f.read()
            if keyword.lower() not in content.lower():
                continue
            idx = content.lower().find(keyword.lower())
            snippet = content[max(0, idx - 60):idx + 120].replace('\n', ' ')
            results.append({**r, 'snippet': snippet})
        except Exception:
            pass

    if not results:
        print(f'No results found for: {keyword}')
        return

    print(f'Found {len(results)} match(es) for "{keyword}":\n')
    for i, r in enumerate(results, 1):
        machine_info = f' [{r["machine"]}]' if len(config) > 1 else ''
        print(f'{i}. [{r["project"]}{machine_info}] {r["date"]}')
        print(f'   ...{r["snippet"]}...')
        print(f'   Path: {r["path"]}')
        print()


def cmd_inspect(config: list[dict], path: str) -> None:
    path = os.path.expanduser(path)
    if not os.path.isfile(path):
        print(f'File not found: {path}', file=sys.stderr)
        sys.exit(1)

    # Detect source type from path
    source_type = 'codex' if 'rollout-' in os.path.basename(path) else 'claude-code'

    print(f'Session: {path}\n')

    try:
        with open(path) as f:
            lines = f.readlines()

        if source_type == 'claude-code':
            msg_num = 0
            for line in lines:
                try:
                    data = json.loads(line)
                except Exception:
                    continue
                role = data.get('type')
                if role == 'user' and not data.get('isMeta'):
                    content = data['message'].get('content', '')
                    if isinstance(content, list):
                        texts = [c.get('text', '') for c in content if c.get('type') == 'text']
                        content = ' '.join(texts)
                    if isinstance(content, str):
                        if '<command-' in content or '<local-command-' in content:
                            continue
                        msg_num += 1
                        ts = data.get('timestamp', '')[:16].replace('T', ' ')
                        print(f'[{msg_num}] USER  {ts}')
                        print(content.strip())
                        print()
                elif role == 'assistant':
                    content = data['message'].get('content', '')
                    if isinstance(content, list):
                        texts = [c.get('text', '') for c in content if c.get('type') == 'text']
                        content = ' '.join(texts)
                    if isinstance(content, str) and content.strip():
                        msg_num += 1
                        ts = data.get('timestamp', '')[:16].replace('T', ' ')
                        print(f'[{msg_num}] ASST  {ts}')
                        print(content.strip()[:500] + ('...' if len(content.strip()) > 500 else ''))
                        print()
        else:  # codex
            msg_num = 0
            for line in lines:
                try:
                    event = json.loads(line)
                except Exception:
                    continue
                if event.get('type') != 'event_msg':
                    continue
                ep = event.get('payload', {})
                msg_type = ep.get('type', '')
                if msg_type == 'user_message':
                    message = ep.get('message', '')
                    if _is_terminal_prompt(message):
                        continue
                    msg_num += 1
                    ts = event.get('timestamp', '')[:16].replace('T', ' ')
                    print(f'[{msg_num}] USER  {ts}')
                    print(message.strip())
                    print()
                elif msg_type == 'assistant_message':
                    message = ep.get('message', '')
                    if message.strip():
                        msg_num += 1
                        ts = event.get('timestamp', '')[:16].replace('T', ' ')
                        print(f'[{msg_num}] ASST  {ts}')
                        print(message.strip()[:500] + ('...' if len(message.strip()) > 500 else ''))
                        print()
    except Exception as e:
        print(f'Error reading file: {e}', file=sys.stderr)
        sys.exit(1)


def cmd_cleanup(config: list[dict]) -> None:
    records = _gather_records(config)
    candidates = []

    seen_first_msgs: dict[str, str] = {}
    for r in records:
        reasons = []

        if r['msgs'] <= 2:
            reasons.append('0–2 user messages')

        low_signal = {'hello', 'hey', 'test', 'config', 'login', 'hi',
                      '收到', '你好', '(system/command only)', '(no user messages)'}
        fm_lower = r['first_msg'].lower().strip()
        if fm_lower in low_signal or fm_lower.startswith('what') and len(fm_lower) < 20:
            reasons.append('low-signal first message')

        # Check for near-duplicates by first message
        key = fm_lower[:40]
        if key in seen_first_msgs:
            reasons.append(f'duplicate topic (see: {seen_first_msgs[key]})')
        else:
            seen_first_msgs[key] = r['path']

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

    # Find the record by scanning the matching source
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
                        help='Also output JSON row→path map')

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
