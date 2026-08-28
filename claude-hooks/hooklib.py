"""Shared bits for the coding-discipline hooks.

Both hooks ask the same two questions -- "is this production source?" and
"where does this session keep its marker?" -- so the answers live here rather
than in each of them. Python puts a script's own directory on the path, so
`import hooklib` works from either.

This file is a copy. The original, and the install.sh that placed and
updates it, live in https://github.com/jam7/ai-dev-gates
"""
import json
import os
import sys

MARKER_DIR = os.environ.get('TMPDIR', '/tmp')

# Languages worth reviewing structurally. Kept explicit: a hook that fires on
# whatever it has not heard of would go off on lockfiles and generated code.
CODE_SUFFIXES = (
    '.dart', '.py', '.ts', '.tsx', '.js', '.jsx', '.go', '.rs', '.java',
    '.kt', '.swift', '.rb', '.cs', '.c', '.h', '.cc', '.cpp', '.hpp',
    '.m', '.mm',
)

# Tests get reviewed differently -- a long, repetitive test is often the
# clearest one -- so they are not what these hooks are about.
TEST_MARKERS = (
    '/test/', '/tests/', '/spec/', '/__tests__/',
    '_test.', '.test.', '_spec.', '.spec.', '/test_',
)

# Nobody wrote these, so nobody should be asked to defend their structure.
NOT_OURS = (
    '/build/', '/.dart_tool/', '/node_modules/', '/vendor/',
    '/third_party/', '/.git/', '/generated/', '.g.dart', '.freezed.dart',
    '/site-packages/', '/.pub-cache/',
)


def is_production_code(path):
    """Source we wrote and would review, as opposed to tests or machinery."""
    if not path or not path.endswith(CODE_SUFFIXES):
        return False
    lowered = path.replace('\\', '/').lower()
    if any(marker in lowered for marker in TEST_MARKERS):
        return False
    return not any(marker in lowered for marker in NOT_OURS)


def marker_for(kind, session):
    return os.path.join(MARKER_DIR, 'claude-%s-%s' % (kind, session))


def read_payload():
    """The hook input, or an empty dict when it is not JSON."""
    try:
        return json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return {}


def project_root(path):
    """The nearest directory above [path] that looks like a repository."""
    current = os.path.dirname(os.path.abspath(path)) if path else os.getcwd()
    while True:
        if os.path.isdir(os.path.join(current, '.git')):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent
