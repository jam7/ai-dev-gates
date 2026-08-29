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
REGISTER = 'tools/register-claude-hooks.py'
METRICS_GATE = 'tools/check-metrics.py'
DELTA = 'tests/deltas'
HOOK_FIXTURES = 'tests/fixtures/hooks'

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
    # One line, many hits: a declared dummy id (vocabulary) or a declared
    # exception (allow) ahead of undeclared ids must not hide them, and two
    # copies of one leaked id are one problem, not two. Reproduces the
    # incident where one declared id at the head of a minified 8 KB line
    # turned the whole line green. The fixtures are .txt so the repository's
    # own gate (default scopes) never scans them; the case names them
    # explicitly. --worktree reads git ls-files, so they must be tracked.
    ('private-multi', 'tools/check-private.py',
     ['--worktree', '--scan-scope', r'^tests/fixtures/private/.*\.txt$',
      '--vocabulary', 'tests/fixtures/private/vocabulary.txt',
      '--allow', 'tests/fixtures/private/private-allow.txt',
      '--denylist', '/dev/null']),
    # A named declaration file that does not exist fails loudly (exit 2)
    # for all three options: it decides what the scan can see, and a trial
    # clone without the private notes repo once got 0 findings from a
    # nonexistent denylist -- the verification passed on nothing. The
    # deliberate-empty idiom (--denylist /dev/null) stays legal and is
    # already pinned by private-multi.
    ('private-missing-denylist', 'tools/check-private.py',
     ['--worktree', '--denylist', 'tests/fixtures/private/no-such.txt']),
    ('private-missing-vocabulary', 'tools/check-private.py',
     ['--worktree', '--vocabulary', 'tests/fixtures/private/no-such.txt']),
    ('private-missing-allow', 'tools/check-private.py',
     ['--worktree', '--allow', 'tests/fixtures/private/no-such.txt']),
    # Denylist boundary rules, one per character class: an ASCII term does
    # not match inside a longer alphanumeric token, a one-or-two-character
    # CJK term matches only next to a delimiter (a bare substring made such
    # names unlistable, so they went unprotected), and a longer CJK title
    # matches anywhere. The denylist fixture is .list so no scope ever scans
    # it and it cannot scream about its own terms.
    ('private-denylist', 'tools/check-private.py',
     ['--worktree', '--scan-scope', r'^tests/fixtures/private/deny/.*\.txt$',
      '--vocabulary', 'tests/fixtures/private/vocabulary.txt',
      '--allow', 'tests/fixtures/private/private-allow.txt',
      '--denylist', 'tests/fixtures/private/deny/denylist.list']),
    # check-text, the one checker that needs an outside runtime. All four of
    # its paths are fixed here with a stand-in textlint, so the cases run on a
    # machine without Node -- which is the very situation the skip path is
    # for. Nothing in scope stays silent (an unrelated commit must not learn
    # whether this machine could have checked it); a missing textlint says so
    # and passes; a present textlint with no configuration fails loudly with
    # exit 2, because a configured check that quietly does nothing is worse
    # than no check.
    ('check-text-out-of-scope', 'tools/check-text.py',
     ['--textlint', '/nonexistent/textlint',
      'tests/fixtures/private/multi.txt']),
    ('check-text-skip', 'tools/check-text.py',
     ['--textlint', '/nonexistent/textlint', 'tests/fixtures/text/sample.md']),
    ('check-text-run', 'tools/check-text.py',
     ['--textlint', 'tests/fixtures/text/fake-textlint.sh',
      '--config', 'tests/fixtures/text/rc.yml',
      'tests/fixtures/text/sample.md']),
    ('check-text-no-config', 'tools/check-text.py',
     ['--textlint', 'tests/fixtures/text/fake-textlint.sh',
      '--config', 'tests/fixtures/text/no-such.yml',
      'tests/fixtures/text/sample.md']),
    # The wrapper finds trace-matrix.py in this repository and passes its
    # arguments through verbatim; without --gate it always runs and prints.
    ('check-trace-pass', 'tools/check-trace.py',
     ['tests/fixtures/trace-gate/clean']),
    # A --code directory that vanished (last test deleted, subpackage moved
    # out) reports the coverage holes, not a usage error -- and does not
    # silently drop the coverage checks either.
    ('trace-missing-code', TRACE,
     ['--code', 'tests/fixtures/trace/no-such-dir',
      'tests/fixtures/trace-gate/clean']),
    # Stale baseline entries are split by cause: a declared function that
    # measures under the threshold is "remove the line", one the analyzer
    # cannot find at all is "verify before removing" (a parser gap once
    # turned a live 73-line declaration into removal advice). A missing
    # file and a dup pair count as resolved. The gate no longer measures
    # the whole scope, so this is its own pass now (--stale): a declaration
    # the gate never re-examines is exactly the one that rots.
    ('check-metrics-stale', METRICS_GATE,
     ['--stale', '--scope', 'tests/fixtures/braces',
      '--baseline', 'tests/fixtures/check-metrics/cq-baseline.txt']),
    # pending: a declared work-in-progress ID hides only its coverage holes
    # and shows them in the summary; an undeclared one still blocks; a
    # declaration that stopped earning its keep (covered, or never defined)
    # is itself reported until removed.
    ('trace-pending', TRACE,
     ['--code', 'tests/fixtures/trace-pending/tests',
      'tests/fixtures/trace-pending/docs']),
    # The settings merge, which edits a file nobody here owns. --dry-run
    # prints the result instead of writing, so the cases pin the merge and
    # touch nothing. A settings file carrying someone else's Stop hook keeps
    # it and gets a group of its own; a second run says so and changes
    # nothing; the same file installed for a project has its commands
    # retargeted rather than duplicated (two copies would both fire); a file
    # that is not the expected shape is refused with exit 2 instead of being
    # guessed at; and no file at all is the fresh-install path.
    ('hooks-register', REGISTER,
     ['--home', '--settings', HOOK_FIXTURES + '/settings-other.json',
      '--dry-run']),
    ('hooks-register-again', REGISTER,
     ['--home', '--settings', HOOK_FIXTURES + '/settings-home.json',
      '--dry-run']),
    ('hooks-register-retarget', REGISTER,
     ['--project', '--settings', HOOK_FIXTURES + '/settings-home.json',
      '--dry-run']),
    ('hooks-register-unreadable', REGISTER,
     ['--home', '--settings', HOOK_FIXTURES + '/settings-broken.json',
      '--dry-run']),
    ('hooks-register-fresh', REGISTER,
     ['--project', '--settings', HOOK_FIXTURES + '/no-such.json',
      '--dry-run']),
    # The gate judges the change, not the repository: a long function that
    # was already there is context and does not block, while a long function
    # and a duplicate the change adds do. --before/--after measures two trees
    # so the delta is pinned without staging anything. The declared run is
    # the same delta with both keys in a baseline: writing the line is what
    # accepting a finding looks like.
    ('metrics-delta', METRICS_GATE,
     ['--before', DELTA + '/before', '--after', DELTA + '/after',
      '--baseline', '/dev/null']),
    ('metrics-delta-declared', METRICS_GATE,
     ['--before', DELTA + '/before', '--after', DELTA + '/after',
      '--baseline', DELTA + '/baseline.txt']),
    # --before without --after is a usage error, not an empty comparison
    # that would report everything as new.
    ('metrics-delta-half', METRICS_GATE, ['--before', DELTA + '/before']),
    # The budget, said out loud rather than spent: two files named with a
    # limit of one is the shape of an import commit meeting max_files. The
    # gate passes -- a change that size is a review, not a gate -- and the
    # reason is on stderr, because going quiet for minutes was the
    # complaint this replaced.
    ('metrics-max-files', METRICS_GATE,
     ['--paths', 'tools/check-refs.py', 'tools/check-text.py',
      '--max-files', '1']),
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
