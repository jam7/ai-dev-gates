#!/usr/bin/env python3
"""Remind Claude to load the coding-rules skill before editing production code.

The rule lives in CLAUDE.md and in a memory, and was still forgotten twice in
one session -- both of those are read once at the start and then have to be
remembered. This fires at the moment of the edit instead, which is the only
place the reminder is cheap to act on.

Once per session, on the first production-source edit, so it does not become
wallpaper. Never blocks: it prints context and exits 0.

This file is a copy. The original, and the install.sh that placed and
updates it, live in https://github.com/jam7/ai-dev-gates
"""
import json
import os
import sys

import hooklib

REMINDER = (
    'First production-code edit this session. If the coding-rules skill has '
    'not been loaded yet, load it now (Skill: coding-rules) and apply the '
    'structural rules while writing -- function length, nesting, duplication, '
    'error handling -- rather than fixing them afterwards. Include the '
    'compliance note when presenting the change.'
)

# Only worth saying where it is true; the gate is one project's, the habit is
# not. Named files rather than a flag, so a project that grows the gate later
# starts getting the sentence without anyone editing this.
GATE = (
    ' This project also gates commits: .githooks/pre-commit runs '
    'tools/check-metrics.py, so a new long function or duplicated block will '
    'block the commit unless it is declared in tools/cq-baseline.txt with a '
    'reason.'
)
GATE_FILES = ('tools/check-metrics.py', 'tools/cq-baseline.txt')


def main():
    payload = hooklib.read_payload()

    path = (payload.get('tool_input') or {}).get('file_path') or ''
    if not hooklib.is_production_code(path):
        return 0

    session = payload.get('session_id') or 'unknown'
    marker = hooklib.marker_for('coding-rules', session)
    if os.path.exists(marker):
        return 0
    try:
        open(marker, 'w').close()
    except OSError:
        pass  # Without the marker it repeats; that is the harmless direction.

    message = REMINDER
    root = hooklib.project_root(path)
    if root and all(os.path.exists(os.path.join(root, f)) for f in GATE_FILES):
        message += GATE

    json.dump({'hookSpecificOutput': {
        'hookEventName': 'PreToolUse',
        'additionalContext': message,
    }}, sys.stdout)
    return 0


if __name__ == '__main__':
    sys.exit(main())
