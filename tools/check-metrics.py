#!/usr/bin/env python3
"""Stop a change from adding structural flags nobody declared.

This file is a copy. The original, and the install.sh that placed and
updates it, live in https://github.com/jam7/ai-dev-gates

cq-metrics.py finds long functions, deep nesting, long parameter lists and
duplicated blocks. Some of what it finds is deliberate -- a byte-for-byte
protocol builder is worth more laid out beside the spec than split up -- so a
plain threshold cannot be a gate.

So the gate is a **declaration**: an accepted flag is a line in the baseline
file with the reason. Anything reported that is not in that file fails the
commit, by name. Writing that line is the review.

What is measured is the change, not the repository (docs/gates/design.md
D-11). Each touched file is measured twice -- as it is now, and as it is in
HEAD -- and only keys that the new version added are the commit's problem.
Legacy code never appears unless the commit touches it, which is what makes
the gate installable in a project that already has code: measured on
llvm/lib/Target/RISCV, the old whole-tree rule asked for 428 written reasons
before the first commit could pass.

Duplication is a comparison, not a measurement, so what it can find is
decided by which files are read together. The corpus is the directory of
each touched file, since a paste usually comes from nearby.

--max-files is the one budget: the most files this will read in a pass,
both versions of them, at roughly 6.5ms a file. It gives way in two steps,
and says so each time rather than going quiet for minutes: past the limit
the neighbours are dropped and duplication is not checked, and past it in
the staged files themselves nothing is measured at all. A commit that
large is a bulk change, which is a human's review, not this one's.

Keys ignore line numbers, since those shift under every edit:

    long <path>::<function>     (also deep, params)
    dup  <path-a>|<path-b>      (the pair, so a second distinct duplicate
                                 between the same two files is not caught)

Usage:
  check-metrics.py                    what the staged change adds (the gate)
  check-metrics.py --paths a.py b.py  what these files add (the Claude hook)
  check-metrics.py --list             the whole scope, to seed the baseline
  check-metrics.py --stale            baseline lines whose finding is gone
  check-metrics.py --before D --after D    two trees, for the tests

Exit: 0 nothing undeclared was added, 1 something was, 2 nothing to measure
with.
"""
import argparse
import collections
import os
import re
import shutil
import subprocess
import sys
import tempfile

DEFAULT_BASELINE = os.path.join('tools', 'cq-baseline.txt')
DEFAULT_MAX_FILES = 400
# What counts as code when this project has not narrowed --ext. cq-metrics
# filters a directory walk by its own list, but a file named explicitly is
# taken as given, and the corpus is named explicitly -- so without this a
# README beside the touched file would be measured as source.
CODE_EXTS = ('.c', '.h', '.cc', '.hh', '.cpp', '.hpp', '.cxx', '.go', '.java',
             '.js', '.ts', '.rs', '.m', '.mm', '.dart', '.kt', '.swift',
             '.cs', '.py')
# cq-metrics.py lives in the cq-review skill, which may be installed in the
# repository (team install) or in the home directory (personal install).
METRICS_ENV = 'CQ_METRICS'
SKILL_REL = os.path.join('.claude', 'skills', 'cq-review', 'cq-metrics.py')

# What one run measures with. Bundled because it is one thing -- where the
# tools are and what this project measures -- and passing the five of them
# around separately put six parameters on measure_change().
Setup = collections.namedtuple(
    'Setup', 'script root ext max_files dup_dirs staged')

SECTION = re.compile(r'^== (Long functions|Deep nesting|Long parameter lists|'
                     r'Duplicated blocks)')
CATEGORY = {
    'Long functions': 'long',
    'Deep nesting': 'deep',
    'Long parameter lists': 'params',
    'Duplicated blocks': 'dup',
}
FINDING = re.compile(r'^\s+(\S+):(\d+)\s+(\S+?)\(\)')
DUP_SITES = re.compile(r'sites:\s*(.+)$')


def repo_root():
    """The repository being checked, or exit 2 when there is no work tree.

    This used to fall back to the directory holding the script, which in a
    bare repository measured a DIFFERENT repository -- the one the script was
    copied into -- and reported the answer as if it were this one's. The same
    fallback was in check-private.py, where it made a safety net report green
    about a repository it had never opened; both were removed together."""
    done = subprocess.run(['git', 'rev-parse', '--show-toplevel'],
                          capture_output=True, text=True)
    if done.returncode == 0 and done.stdout.strip():
        return done.stdout.strip()
    sys.stderr.write(
        'no work tree here, so there is no repository to check.\n'
        'A bare repository or a bundle has to be checked from a clone with a\n'
        'work tree: git clone <it> tmp && cd tmp && <this script>\n')
    sys.exit(2)


def metrics_script(root):
    """Where cq-metrics.py is, or None if it is not installed."""
    for path in (os.environ.get(METRICS_ENV),
                 os.path.join(root, SKILL_REL),
                 os.path.expanduser(os.path.join('~', SKILL_REL))):
        if path and os.path.exists(path):
            return path
    return None


def parse_keys(report):
    """Turn a cq-metrics report into {key: the line it came from}."""
    keys, category = {}, None
    for line in report.split('\n'):
        header = SECTION.match(line)
        if header:
            category = CATEGORY[header.group(1)]
            continue
        if line.startswith('== ') or not line.strip() or category is None:
            continue
        if category == 'dup':
            sites = DUP_SITES.search(line)
            if sites:
                files = sorted({s.strip().rsplit(':', 1)[0]
                                for s in sites.group(1).split(',')})
                keys['dup ' + '|'.join(files)] = line.strip()
            continue
        found = FINDING.match(line)
        if found:
            keys['%s %s::%s' % (category, found.group(1), found.group(3))] = \
                line.strip()
    return keys


def run_metrics(script, cwd, paths, ext=None, dup=True):
    """cq-metrics over [paths], relative to [cwd]. Returns {key: line}.

    A path absent from this tree is dropped rather than passed on: the file a
    change adds has no version in HEAD, and cq-metrics exits 2 on a path it
    cannot open. Everything such a file contains is then new, which is what
    an added file means.
    """
    here = [p for p in paths if os.path.exists(os.path.join(cwd, p))]
    if not here:
        return {}
    cmd = [sys.executable, script, '--top', '100000']
    if ext:
        cmd += ['--ext', ext]
    if not dup:
        cmd += ['--dup-window', '0']
    done = subprocess.run(cmd + here, cwd=cwd, capture_output=True,
                          text=True, check=True)
    return parse_keys(done.stdout)


def git_lines(root, args):
    done = subprocess.run(['git'] + args, cwd=root, capture_output=True,
                          text=True)
    return [line for line in done.stdout.split('\n') if line]


def wanted(path, ext, scopes):
    """Is this file one this project measures?

    A scope entry is a directory prefix or the file itself, so `scope` in
    gate.conf can name one file where a directory is too coarse (D-19).
    """
    suffix = os.path.splitext(path)[1]
    if suffix not in (ext.split(',') if ext else CODE_EXTS):
        return False
    if not scopes:
        return True
    return any(path == s or path.startswith(s.rstrip('/') + '/')
               for s in scopes)


def staged_paths(root, ext, scopes):
    """Repository-relative paths this commit adds, copies or modifies."""
    names = git_lines(root, ['diff', '--cached', '--name-only',
                             '--diff-filter=ACM'])
    return sorted(p for p in names if wanted(p, ext, scopes))


def files_in(root, directory, ext):
    """The measurable files directly in [directory], not recursive.

    The extension is checked before the entry is asked whether it is a file:
    in a directory of thousands, that is the difference between one syscall
    per candidate and one per entry. scandir carries the answer from the
    directory read, so most entries cost nothing at all.
    """
    here = os.path.join(root, directory)
    if not os.path.isdir(here):
        return set()
    found = set()
    with os.scandir(here) as entries:
        for entry in entries:
            rel = os.path.normpath(os.path.join(directory, entry.name))
            if wanted(rel, ext, None) and entry.is_file():
                found.add(rel)
    return found


def dup_corpus(setup, targets):
    """The files duplication is looked for in, and why it may be empty.

    The directory of each touched file, not recursive: a paste usually comes
    from a neighbour, and the cost is what bounds this (design.md D-14, D-15).
    """
    root, ext, cap = setup.root, setup.ext, setup.max_files
    found = set(targets)
    # One directory, however many of the touched files are in it: reading it
    # once per file was the same listing over and over.
    directories = setup.dup_dirs or {os.path.dirname(t) for t in targets}
    for directory in sorted(directories):
        found |= files_in(root, directory, ext)
        if len(found) > cap:
            break  # over budget already; the rest would not change that
    if len(found) > cap:
        return sorted(targets), ('duplication not checked: the corpus around '
                                 'these files is %d files, over the %d limit '
                                 '(--max-files, or max_files in gate.conf). '
                                 'cq-review measures it in full.'
                                 % (len(found), cap))
    return sorted(found), None


def blob(root, rev, path):
    """A file's content at [rev] ('' for the index), or None if absent."""
    done = subprocess.run(['git', 'show', '%s:%s' % (rev, path)], cwd=root,
                          capture_output=True)
    return done.stdout if done.returncode == 0 else None


def read(root, rel):
    with open(os.path.join(root, rel), 'rb') as f:
        return f.read()


def differs_from_index(root):
    """Paths whose work tree copy is not what is staged.

    Everything else can be read from disk instead of asked of git, which is
    one process per file saved -- and in a commit, almost every staged file
    is exactly what is on disk.
    """
    return set(git_lines(root, ['diff', '--name-only']))


def plant(dest, rel, content):
    target = os.path.join(dest, rel)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, 'wb') as f:
        f.write(content)


def build_trees(setup, targets, corpus):
    """Two copies of [corpus]: as HEAD has it, and as the change leaves it.

    Only the touched files differ between them, so the rest is copied from
    the work tree once for each side. Returns (before, after, temp) where a
    file missing from HEAD simply does not appear in before -- everything it
    contains is then an addition, which is what a new file is.
    """
    root = setup.root
    temp = tempfile.mkdtemp(prefix='cq-metrics-')
    before, after = os.path.join(temp, 'before'), os.path.join(temp, 'after')
    unstaged = differs_from_index(root) if setup.staged else set()
    in_head = False
    for rel in corpus:
        if rel in targets:
            continue
        content = read(root, rel)
        plant(before, rel, content)
        plant(after, rel, content)
    for rel in targets:
        old = blob(root, 'HEAD', rel)
        if old is not None:
            plant(before, rel, old)
            in_head = True
        new = blob(root, '', rel) if rel in unstaged else read(root, rel)
        plant(after, rel, new if new is not None else read(root, rel))
    return before, after, temp, in_head


def measure_change(setup, targets):
    """Keys the change added, keys it left alone, and any corpus notice.

    Two passes over the corpus, one per version, except when no touched file
    exists in HEAD at all: the neighbours are byte-identical copies in both
    trees, so their keys cannot differ, and every key naming a touched file
    is then new by definition. That is the first commit, and every commit
    that only adds files.
    """
    targets = set(targets)
    corpus, notice = dup_corpus(setup, sorted(targets))
    before, after, temp, in_head = build_trees(setup, targets, corpus)
    try:
        dup = notice is None
        new = run_metrics(setup.script, after, corpus, setup.ext, dup)
        old = (run_metrics(setup.script, before, corpus, setup.ext, dup)
               if in_head else {})
    finally:
        shutil.rmtree(temp, ignore_errors=True)
    added = {k: v for k, v in new.items()
             if k not in old and touches(k, targets)}
    kept = {k: v for k, v in new.items() if k in old and touches(k, targets)}
    return added, kept, notice


def touches(key, targets):
    """Does this key name one of the files the change touched?"""
    ref = key.split(' ', 1)[1]
    files = ref.split('|') if key.startswith('dup ') else [ref.split('::')[0]]
    return any(f in targets for f in files)


def functions_seen(script, root, paths):
    """Every path::function the analyzer finds in [paths], flagged or not.

    Thresholds at their minimum turn the run into an inventory: the deep and
    params sections list every function, including empty ones.
    """
    cmd = [sys.executable, script, '--max-func-lines', '0', '--max-nest', '-1',
           '--max-params', '-1', '--dup-window', '0', '--top', '100000']
    done = subprocess.run(cmd + paths, cwd=root, capture_output=True,
                          text=True, check=True)
    return {key.split(' ', 1)[1] for key in parse_keys(done.stdout)}


def split_gone(gone, script, root):
    """Split stale keys into (resolved, unseen).

    A resolved flag names a function the analyzer still sees, so measuring
    under the threshold is a real improvement. An unseen one means the
    function itself was not found: a deletion, a rename, or a parser gap --
    the report must not present those as improvements. A key whose file is
    gone is resolved (the code is gone with it), and dup keys name file
    pairs, not functions, so they cannot be told apart and stay resolved.
    """
    targets, resolved = {}, []
    for key in gone:
        category, _, ref = key.partition(' ')
        if category in ('long', 'deep', 'params') and '::' in ref \
                and os.path.isfile(os.path.join(root, ref.split('::', 1)[0])):
            targets.setdefault(ref.split('::', 1)[0], []).append(key)
        else:
            resolved.append(key)
    if not targets:
        return sorted(resolved), []
    seen = functions_seen(script, root, sorted(targets))
    unseen = [key for keys in targets.values() for key in keys
              if key.split(' ', 1)[1] not in seen]
    resolved += [key for keys in targets.values() for key in keys
                 if key.split(' ', 1)[1] in seen]
    return sorted(resolved), sorted(unseen)


def baseline_keys(path):
    if not os.path.exists(path):
        return set()
    keys = set()
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.split('#', 1)[0].strip()
            if line:
                keys.add(line)
    return keys


def report(added, kept, notice, baseline_name):
    """Print what the change added. Returns the exit status."""
    if notice:
        print(notice, file=sys.stderr)
    if kept:
        print('Already there before this change (nothing to answer for):',
              file=sys.stderr)
        for key in sorted(kept):
            print('  %s' % kept[key], file=sys.stderr)
        print(file=sys.stderr)
    if not added:
        return 0
    print('This change adds structural findings that are not declared:',
          file=sys.stderr)
    for key in sorted(added):
        print('  %s' % added[key], file=sys.stderr)
    print(file=sys.stderr)
    print('Either restructure, or add the key to %s with the reason it is '
          'worth keeping.' % baseline_name, file=sys.stderr)
    print('The keys are:', file=sys.stderr)
    for key in sorted(added):
        print('  %s' % key, file=sys.stderr)
    return 1


def whole_scope(script, root, scopes, ext):
    """Every key in the configured scope, or 2 if there is nothing to walk.

    A scope entry may name a single file as well as a directory (D-19): the
    staged filter has always accepted one, and this pass dropped it, so the
    same gate.conf line meant two different things depending on which ran.
    """
    paths = [p for p in (scopes or ['.'])
             if os.path.exists(os.path.join(root, p))]
    if not paths:
        print('none of the measured paths (%s) exist here.'
              % ', '.join(scopes or ['.']), file=sys.stderr)
        return 2, {}
    return 0, run_metrics(script, root, paths, ext)


def stale(script, root, args):
    """Baseline lines whose finding is no longer there.

    The gate measures only what a change touches, so a declaration is never
    re-examined by it: an accepted finding that has since been restructured
    keeps its line forever, and the file fills with decisions nobody holds
    any more. This is the pass that finds them, run when you want to prune
    (docs/gates/design.md D-17).
    """
    status, current = whole_scope(script, root, args.scope, args.ext)
    if status:
        return status
    baseline = args.baseline
    if not os.path.isabs(baseline):
        baseline = os.path.join(root, baseline)
    declared = baseline_keys(baseline)
    resolved, unseen = split_gone(
        sorted(k for k in declared if k not in current), script, root)
    return report_stale(resolved, unseen, args.baseline)


def report_stale(resolved, unseen, baseline_name):
    if resolved:
        print('No longer flagged -- remove these from %s:' % baseline_name,
              file=sys.stderr)
        for key in resolved:
            print('  %s' % key, file=sys.stderr)
        print(file=sys.stderr)
    if unseen:
        print('Declared, but the function itself is not seen by the '
              'analyzer:', file=sys.stderr)
        for key in unseen:
            print('  %s' % key, file=sys.stderr)
        print('If it was deleted or renamed, remove the line from %s. If the '
              'code is still\nthere, this is a measurement gap, not an '
              'improvement: keep the line and report\nthe parser miss.'
              % baseline_name, file=sys.stderr)
    return 1 if (resolved or unseen) else 0


def parse_args():
    ap = argparse.ArgumentParser(
        description='Fail on structural findings a change adds undeclared.')
    ap.add_argument('--list', action='store_true',
                    help='print every key in the scope, to seed the baseline')
    ap.add_argument('--stale', action='store_true',
                    help='report baseline lines whose finding is gone')
    ap.add_argument('--paths', nargs='+', metavar='FILE',
                    help='measure these files instead of the staged ones')
    ap.add_argument('--before', metavar='DIR',
                    help='with --after: compare two trees (for the tests)')
    ap.add_argument('--after', metavar='DIR', help='see --before')
    ap.add_argument('--scope', action='append', metavar='PATH',
                    help='directory or file to measure, repeatable '
                         '(default: the whole repository)')
    ap.add_argument('--ext', metavar='.a,.b',
                    help='extensions to measure, passed to cq-metrics.py')
    ap.add_argument('--baseline', metavar='PATH', default=DEFAULT_BASELINE,
                    help='declaration file (default: %s)' % DEFAULT_BASELINE)
    ap.add_argument('--dup-corpus', action='append', metavar='DIR',
                    help='look for duplication in these directories instead '
                         'of the ones the touched files are in, repeatable')
    ap.add_argument('--max-files', type=int, metavar='N',
                    default=DEFAULT_MAX_FILES,
                    help='the most files to read in a pass: past it the '
                         'duplication corpus is dropped, and past it in the '
                         'change itself nothing is measured (default %d)'
                         % DEFAULT_MAX_FILES)
    return ap.parse_args()


def compare_trees(script, args):
    """--before/--after: the delta between two directories, undeclared only."""
    old = run_metrics(script, args.before, ['.'], args.ext)
    new = run_metrics(script, args.after, ['.'], args.ext)
    added = {k: v for k, v in new.items() if k not in old}
    kept = {k: v for k, v in new.items() if k in old}
    declared = baseline_keys(args.baseline)
    return report({k: v for k, v in added.items() if k not in declared},
                  kept, None, args.baseline)


def gate(script, root, args):
    """The change this run is about: staged, or the files it was given."""
    if args.paths:
        targets = [p for p in args.paths
                   if os.path.isfile(os.path.join(root, p))]
    else:
        targets = staged_paths(root, args.ext, args.scope)
    if not targets:
        return 0
    if len(targets) > args.max_files:
        print('structure check skipped: this change is %d files, over the %d '
              'limit (--max-files, or max_files in gate.conf). A change that '
              'size is a review, not a gate; cq-review measures the result.'
              % (len(targets), args.max_files), file=sys.stderr)
        return 0

    baseline = args.baseline
    if not os.path.isabs(baseline):
        baseline = os.path.join(root, baseline)
    declared = baseline_keys(baseline)
    setup = Setup(script, root, args.ext, args.max_files,
                  args.dup_corpus, staged=not args.paths)
    added, kept, notice = measure_change(setup, targets)
    added = {k: v for k, v in added.items() if k not in declared}
    return report(added, kept, notice, args.baseline)


def main():
    args = parse_args()
    root = repo_root()
    script = metrics_script(root)
    if script is None:
        # Without cq-metrics.py there is nothing to measure, and someone
        # else's commit is not the place to complain about that.
        print('cq-metrics.py not found in %s or ~/%s; skipping the structure '
              'check.' % (root, SKILL_REL), file=sys.stderr)
        print('Set %s to point at it.' % METRICS_ENV, file=sys.stderr)
        return 0

    if args.before or args.after:
        if not (args.before and args.after):
            print('--before needs --after', file=sys.stderr)
            return 2
        return compare_trees(script, args)
    if args.stale:
        return stale(script, root, args)
    if args.list:
        status, current = whole_scope(script, root, args.scope, args.ext)
        for key in sorted(current):
            print(key)
        return status
    return gate(script, root, args)


if __name__ == '__main__':
    sys.exit(main())
