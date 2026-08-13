#!/usr/bin/env python3
"""Golden-output tests for the bundled scripts.

These record what the scripts do today, not what they ought to do. The point
is to make a refactoring visible: if the output moves, either the change was
wrong or the golden file needs updating for a reason you can name in the
commit message. There is nothing else guarding these scripts.

Each case fixes decisions that are otherwise invisible -- an elif chain counts
as one level, a Go import block is not duplication, `using var x = ...` is a
statement and not an import. Thresholds are pushed to their minimum in the
inventory case so that every function is listed with its numbers, including
the ones no threshold would flag.

Usage:
  tests/run.py            run every case, report differences, exit 1 on any
  tests/run.py --update   rewrite the golden files from the current output
  tests/run.py --list     print the case names
"""
import argparse
import difflib
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLDEN = os.path.join(ROOT, 'tests', 'golden')
METRICS = '.claude/skills/cq-review/cq-metrics.py'
TRACE = '.claude/skills/spec-dev/trace-matrix.py'
COUPLING = '.claude/skills/cq-review/cpp-coupling.py'
REFS = 'tools/check-refs.py'

CASES = [
    # Every function with its length, depth and parameter count.
    ('metrics-inventory', METRICS, [
        '--max-func-lines', '0', '--max-nest', '-1', '--max-params', '-1',
        '--dup-window', '0', '--top', '500', 'tests/fixtures']),
    # What a normal run reports, including which duplicates survive the
    # import filter.
    ('metrics-defaults', METRICS, [
        '--max-func-lines', '12', '--max-nest', '2', '--max-params', '4',
        '--top', '500', 'tests/fixtures']),
    # The duplicate window at its smallest: import blocks would flood this if
    # they were not dropped.
    ('metrics-dup-window-4', METRICS, [
        '--max-func-lines', '999', '--max-nest', '99', '--max-params', '99',
        '--dup-window', '4', '--top', '500', 'tests/fixtures']),
    ('metrics-csv', METRICS, [
        '--csv', '--label', 'fixture', 'tests/fixtures']),
    # Error paths. They are the easiest thing to change by accident while
    # rearranging option handling, and no other case reaches them.
    ('metrics-no-paths', METRICS, []),
    ('metrics-missing-int', METRICS, ['--max-nest']),
    ('metrics-missing-ext', METRICS, ['--ext']),
    ('metrics-bad-int', METRICS, ['--max-nest', 'x', 'tests/fixtures']),
    ('metrics-no-match', METRICS, ['--ext', '.zzz', 'tests/fixtures']),
    # A cycle (core <-> net), a stable module depended on by both (util,
    # Ca=2 I=0.00), and the summary counts.
    ('coupling-report', COUPLING, [
        '--root', 'tests/fixtures/coupling/src', '--module-depth', '1',
        'tests/fixtures/coupling/compile_commands.json']),
    ('coupling-csv', COUPLING, [
        '--csv', '--root', 'tests/fixtures/coupling/src', '--module-depth', '1',
        'tests/fixtures/coupling/compile_commands.json']),
    ('coupling-fail-on-cycle', COUPLING, [
        '--fail-on-cycle', '--root', 'tests/fixtures/coupling/src',
        '--module-depth', '1',
        'tests/fixtures/coupling/compile_commands.json']),
    ('trace-matrix', TRACE, [
        '--code', 'tests/fixtures/trace/tests', 'tests/fixtures/trace/docs']),
    ('trace-matrix-matrix', TRACE, [
        '--matrix', '--code', 'tests/fixtures/trace/tests',
        'tests/fixtures/trace/docs']),
    # The gate checks: exactly the section missing its subheading is named
    # (an ad-hoc one-liner once reported all 10 when 3 were missing), a
    # declared word/heading exception passes, and an undeclared ambiguous
    # word is reported with its section.
    ('trace-gate', TRACE, ['tests/fixtures/trace-gate/docs']),
    # Fully compliant documents pass the gates with exit 0, no gate file.
    ('trace-gate-clean', TRACE, ['tests/fixtures/trace-gate/clean']),
    # The retirement ledger: a retired ID is a valid reference target and
    # exempt from coverage, a live heading claiming one is reported, and a
    # retired number that is defined again is reported (never reused).
    # Reproduces the incident where a withdrawn R-05 made exit 1 permanent.
    ('trace-retire', TRACE, ['--matrix', 'tests/fixtures/trace-retire/docs']),
    # Hash-shaped tokens in tracking documents are flagged alive or dead;
    # dates, decimal ids and hex-only English words stay quiet. --allow
    # /dev/null: this repository's own refs-allow.txt declares the planted
    # tokens so that committing the fixtures passes its own gate.
    ('refs-hit', REFS, ['--allow', '/dev/null', 'tests/fixtures/refs/bad']),
    # A declared checksum passes: the declaration path.
    ('refs-allow', REFS, ['--allow', 'tests/fixtures/refs/allow/refs-allow.txt',
                          'tests/fixtures/refs/allow/docs']),
]


def run_case(script, args):
    """Output of one case, with the exit status recorded alongside it.

    The repository path is masked: a traceback prints absolute paths, and a
    golden file that only matches on one machine is worse than none.
    """
    done = subprocess.run([sys.executable, script] + args, cwd=ROOT,
                          capture_output=True, text=True)
    text = (done.stdout + done.stderr).rstrip('\n').replace(ROOT, '<root>')
    return '%s\n--- exit %d ---\n' % (text, done.returncode)


def golden_path(name):
    return os.path.join(GOLDEN, name + '.txt')


def update(cases):
    os.makedirs(GOLDEN, exist_ok=True)
    for name, script, args in cases:
        with open(golden_path(name), 'w', encoding='utf-8') as f:
            f.write(run_case(script, args))
        print('wrote %s' % os.path.relpath(golden_path(name), ROOT))
    return 0


def compare(cases):
    failed = 0
    for name, script, args in cases:
        actual = run_case(script, args)
        path = golden_path(name)
        if not os.path.exists(path):
            print('MISSING GOLDEN  %s (run --update)' % name)
            failed += 1
            continue
        with open(path, encoding='utf-8') as f:
            expected = f.read()
        if actual == expected:
            print('ok    %s' % name)
            continue
        failed += 1
        print('FAIL  %s' % name)
        for line in difflib.unified_diff(
                expected.splitlines(), actual.splitlines(),
                'golden', 'actual', lineterm=''):
            print('    %s' % line)
    print('\n%d case(s), %d failed' % (len(cases), failed))
    return 1 if failed else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--update', action='store_true',
                    help='rewrite the golden files from the current output')
    ap.add_argument('--list', action='store_true', help='print case names')
    args = ap.parse_args()
    if args.list:
        for name, _, _ in CASES:
            print(name)
        return 0
    return update(CASES) if args.update else compare(CASES)


if __name__ == '__main__':
    sys.exit(main())
