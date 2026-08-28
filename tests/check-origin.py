#!/usr/bin/env python3
"""This repository must use the originals it ships, byte for byte.

Every *.template.* file here is what install.sh puts into someone else's
project. This repository has its own copy of two of them -- CLAUDE.md and
the active coding rules -- and those copies are not customisations: they
are what the package recommends, being run by the package. A difference
means the original was edited and the copy was forgotten, and nobody
notices, because a stale convention still reads like a convention.

Measured (2026-08-28): the commit "spec-dev: notes/ as its own private
repository is a supported shape" added the "no programs in notes/" rule to
CLAUDE.template.md and not to this repository's CLAUDE.md, which then went
five commits without it. install.sh could never have fixed that -- a
project install skips its own repository, and an existing CLAUDE.md is
never replaced (ADR-001), so there is no path but this check.

Not a distributed gate: a consumer project's CLAUDE.md and rules are meant
to differ from the templates. This one is the origin, and only the origin
has this obligation. Run from the commit gate via gate.conf's extra_checks.

Usage: tests/check-origin.py     (0 clean, 1 a copy has fallen behind)
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES = os.path.join('.claude', 'skills', 'coding-rules', 'rules')
SUFFIX = '.template.md'


def pairs():
    """(original, copy) for every template whose copy this repository runs."""
    found = [('CLAUDE.template.md', 'CLAUDE.md')]
    rules = os.path.join(ROOT, RULES)
    for name in sorted(os.listdir(rules)):
        if name.endswith(SUFFIX):
            active = name[:-len(SUFFIX)] + '.md'
            found.append((os.path.join(RULES, name),
                          os.path.join(RULES, active)))
    return found


def read(path):
    with open(os.path.join(ROOT, path), encoding='utf-8') as f:
        return f.read()


def main():
    behind = []
    for template, active in pairs():
        if not os.path.exists(os.path.join(ROOT, active)):
            behind.append((template, active, 'missing'))
        elif read(template) != read(active):
            behind.append((template, active, 'differs'))

    if not behind:
        return 0

    print('These copies no longer match the originals this package ships:',
          file=sys.stderr)
    for template, active, how in behind:
        print('  %s %s %s' % (active, how, template), file=sys.stderr)
    print(file=sys.stderr)
    for line in (
        'This repository runs what it recommends, so the two are the same',
        'file. Copy the original over the copy -- and if the change belongs',
        'only here, it does not: put it in the template, where every project',
        'gets it (docs/install/design.md D-05).',
    ):
        print(line, file=sys.stderr)
    return 1


if __name__ == '__main__':
    sys.exit(main())
