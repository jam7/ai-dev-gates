#!/usr/bin/env python3
"""Do not let a turn that changed production code end without its review note.

Two hooks share this file:

  --touched   PostToolUse on Edit|Write. Notes that this turn changed
              production source, by writing the path into a marker.
  --check     Stop. If the marker is there, measures those files against
              their version in HEAD and looks at what was actually said this
              turn; if the note is missing, or does not answer for a finding
              the turn added, it blocks the stop and asks, then clears the
              marker so the next stop goes through.

The measurement is tools/check-metrics.py, run over the touched files only
(docs/gates/design.md D-10). It is the same judgement the commit gate makes,
so what passes here passes there. Where the project does not have it, the
note is still asked for and nothing is measured -- this half of the gate is
a convenience, not the guarantee.

Why at Stop rather than at the edit: the note is written when the work is
presented, and by then the edit is thousands of tokens in the past. This is
the one moment where the reminder and the action are adjacent.

The check reads the session transcript, which Claude Code writes live to
~/.claude/projects/<sanitised-cwd>/<session-id>.jsonl. If it cannot be read,
the hook blocks anyway: a false reminder costs a sentence, a missed one costs
the review.

This file is a copy. The original, and the install.sh that placed and
updates it, live in https://github.com/jam7/ai-dev-gates
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

import hooklib

PROJECTS = os.path.expanduser('~/.claude/projects')

# What counts as having written the note. Any one of these is enough; the
# point is to catch silence, not to police the wording.
WROTE_NOTE = re.compile(r'準拠メモ|coding-rules 準拠|compliance note')

ASK = (
    'This turn changed production code and is ending without a review note. '
    'Before finishing, state: (1) the coding-rules files loaded and which '
    'rule actually bit, (2) anything where the existing style won over a '
    'rule, (3) PERF-1/PERF-2 if complexity or memory changed, (4) deviations '
    'and why, and (5) what you could not verify yourself and want checked on '
    'the device. If the note is already above, say so in one line and stop.'
)

# The note is there, but a finding this turn added is not named in it. The
# whole value of the note is that the decision was made and written down; a
# note that skips the one measurable thing is the case this hook exists for.
ANSWERED_NOTHING = (
    'The review note is there, but it does not name a structural finding '
    'this turn added. Name the key in the note with the reason it is worth '
    'keeping, or restructure and edit again.'
)

# Measured, so it is not the author's word against the reader's. Keys are
# printed the way the baseline file wants them, so accepting one is a copy.
MEASURED = (
    '\n\nMeasured over the files this turn wrote:\n\n%s\n\n'
    'A finding listed as added is this change\'s: name its key in the note '
    'with the reason it is worth keeping, or restructure and edit again. '
    'One listed as already there is context, not something to answer for. '
    'The commit gate makes the same judgement, so what passes here passes '
    'there.'
)


def marker_for(session):
    return hooklib.marker_for('quality-note', session)


def touched(payload):
    """Production source was written: remember which file, for the stop."""
    path = (payload.get('tool_input') or {}).get('file_path') or ''
    if not hooklib.is_production_code(path):
        return 0
    session = payload.get('session_id')
    if not session:
        return 0
    try:
        with open(marker_for(session), 'a', encoding='utf-8') as f:
            f.write(path + '\n')
    except OSError:
        pass
    return 0


def marked_files(marker):
    """The paths this turn wrote, in order, without repeats."""
    try:
        with open(marker, encoding='utf-8') as f:
            paths = [line.strip() for line in f if line.strip()]
    except OSError:
        return []
    return sorted({p for p in paths if os.path.isfile(p)})


def measure(paths):
    """What check-metrics says about these files: (report, added keys).

    The report is empty when the change added nothing and the files carried
    nothing worth mentioning, and None where there is nothing to measure
    with -- no work tree, no check-metrics.py, or no file inside the project.
    Both halves are always returned: the caller unpacks the pair, so a bare
    None here ended the hook in a traceback on every project without the
    checker.
    """
    root = hooklib.project_root(paths[0])
    if not root:
        return None, []
    script = os.path.join(root, 'tools', 'check-metrics.py')
    if not os.path.exists(script):
        return None, []
    inside = [os.path.relpath(p, root) for p in paths
              if p.startswith(root + os.sep)]
    if not inside:
        return None, []
    exts = sorted({os.path.splitext(p)[1] for p in inside})
    cmd = [sys.executable, script, '--paths'] + inside
    done = subprocess.run(cmd + ['--ext', ','.join(exts)], cwd=root,
                          capture_output=True, text=True)
    return done.stderr.strip(), added_keys(done.stderr)


def added_keys(report):
    """The keys check-metrics listed as added, which the note must name."""
    keys, listing = [], False
    for line in report.split('\n'):
        if line.startswith('The keys are:'):
            listing = True
        elif listing and line.startswith('  '):
            keys.append(line.strip())
        elif listing and line.strip():
            break
    return keys


def transcript_path(payload):
    """Where this session is being written, as given or by convention."""
    given = payload.get('transcript_path')
    if given and os.path.exists(given):
        return given
    session = payload.get('session_id')
    if not session:
        return None
    cwd = payload.get('cwd') or os.getcwd()
    sanitised = cwd.replace('/', '-')
    guess = os.path.join(PROJECTS, sanitised, '%s.jsonl' % session)
    return guess if os.path.exists(guess) else None


def said_since(path, since, lines=600):
    """The assistant's own words written after [since], a UTC timestamp.

    Bounded to this turn on purpose. Searching the whole tail would find the
    note written three turns ago and stay quiet about the one missing now,
    which is the failure this hook exists to catch.
    """
    said = []
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            tail = f.readlines()[-lines:]
    except OSError:
        return None
    for line in tail:
        try:
            record = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        stamp = record.get('timestamp') or ''
        if stamp < since:
            continue
        message = record.get('message') or {}
        if message.get('role') != 'assistant':
            continue
        content = message.get('content')
        if not isinstance(content, list):
            continue
        for part in content:
            if part.get('type') == 'text':
                said.append(part.get('text') or '')
    return '\n'.join(said)


def check(payload):
    session = payload.get('session_id')
    if not session:
        return 0
    marker = marker_for(session)
    if not os.path.exists(marker):
        return 0
    files = marked_files(marker)
    # The marker was written when the edit happened, so its own mtime is
    # where this turn's code changes started.
    edited_at = time.strftime('%Y-%m-%dT%H:%M:%S',
                              time.gmtime(os.path.getmtime(marker)))

    # Clear it first, whatever happens next: a marker that outlives its turn
    # would ask again on a turn that changed nothing, and a block that cannot
    # clear itself is a loop.
    try:
        os.remove(marker)
    except OSError:
        pass

    report, keys = measure(files) if files else (None, [])
    path = transcript_path(payload)
    said = said_since(path, edited_at) if path else None
    wrote_note = said is not None and WROTE_NOTE.search(said)
    unanswered = [k for k in keys if said is None or k not in said]
    if wrote_note and not unanswered:
        return 0

    reason = ASK if not wrote_note else ANSWERED_NOTHING
    if report:
        reason += MEASURED % report
    json.dump({'decision': 'block', 'reason': reason}, sys.stdout)
    return 0


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--touched', action='store_true')
    group.add_argument('--check', action='store_true')
    args = parser.parse_args()

    payload = hooklib.read_payload()
    return touched(payload) if args.touched else check(payload)


if __name__ == '__main__':
    sys.exit(main())
