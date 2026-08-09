#!/usr/bin/env python3
"""Stop private data from reaching a repository it must not reach.

Written for a public repository whose developer's real data (share layout,
work titles, server ids) is not public. Rules in CLAUDE.md were not enough --
real paths leaked several times, in separate sessions, because test data gets
written by copying whatever was on screen in a log. This turns the rule into a
gate that does not depend on anyone remembering it.

Two kinds of check:

* Structural -- absolute home paths, private IPs, long numeric ids. These
  patterns are wrong wherever they appear, so every scanned file gets them.

* Vocabulary (the important one) -- in test data and documentation examples,
  anything that looks like content (a path with separators, a media filename,
  any CJK text) must be built from the vocabulary file. A denylist can only
  catch names someone thought to list; a vocabulary catches the name nobody
  knew about, which is exactly the case that keeps happening.

  The vocabulary check runs only when the vocabulary file exists. Without it
  every invented path would fail, so a project that has not written one yet
  gets the structural checks and nothing else.

An optional exact denylist is read from notes/private-patterns.txt when that
file exists. It lists real names, so it belongs in a private notes repository
and never in the checked one -- a list of things that must not leak is itself
the worst thing to leak.

Usage:
  check-private.py --staged            what is about to be committed
  check-private.py --range A..B        every revision in a range, and messages
  check-private.py --all-history       every revision that exists
  check-private.py --worktree          the files on disk right now

  --vocabulary PATH   default tools/test-vocabulary.txt
  --denylist PATH     default notes/private-patterns.txt
  --data-scope RE     files whose data must use the vocabulary, repeatable
  --scan-scope RE     files scanned at all (defaults to the data scope plus
                      lib/ and src/), repeatable
"""
import argparse
import os
import re
import subprocess
import sys

DEFAULT_VOCAB = os.path.join('tools', 'test-vocabulary.txt')
DEFAULT_DENYLIST = os.path.join('notes', 'private-patterns.txt')

SOURCE_EXT = (r'\.(dart|py|js|jsx|ts|tsx|go|java|kt|rs|c|cc|cpp|cxx|h|hpp|'
              r'swift|rb|php|cs|scala|m|mm)$')
# Files whose string literals and code examples must use the vocabulary.
DEFAULT_DATA_SCOPE = (
    r'(^|/)tests?/.*' + SOURCE_EXT,
    r'(^|/)docs?/.*\.md$',
    r'^[^/]*\.md$',
)
# Everything scanned at all. Production code is here for the structural checks
# only: its localized UI strings are legitimate content, not test data.
DEFAULT_SCAN_SCOPE = DEFAULT_DATA_SCOPE + (
    r'(^|/)(lib|src)/.*' + SOURCE_EXT,
)

CJK = re.compile(r'[぀-ヿ㐀-䶿一-鿿]')
# `$e\n$st` in a logging example is one string, not a two-segment path. A real
# path carries a dot, a slash or a drive colon; an escape sequence does not.
ESCAPE_NOT_PATH = re.compile(r'^[^/:.]*\\[nrt0v][^/:.]*$')
MEDIA = re.compile(r'\.(pdf|zip|cbz|rar|jpe?g|png|gif|webp|mp4|mkv|avi|webm'
                   r'|mov|wmv|ts|m4v)$', re.I)

STRUCTURAL = [
    # Case-sensitive on purpose: `/Home/End` is a pair of keys and
    # `pixiv.net/users/123` is a URL, and both matched when it was not.
    (re.compile(r'(?<![\w/.])/home/[a-z0-9_.-]+'), 'absolute home path'),
    (re.compile(r'(?<![\w/.])/Users/[A-Za-z0-9_.-]+'), 'absolute home path'),
    (re.compile(r'[A-Z]:\\\\?Users\\\\?[a-z0-9_.-]+', re.I), 'absolute home path'),
    (re.compile(r'\b192\.168\.\d{1,3}\.\d{1,3}\b'), 'private IP address'),
    (re.compile(r'\b10\.\d{1,3}\.\d{1,3}\.\d{1,3}\b'), 'private IP address'),
    (re.compile(r'\b172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}\b'), 'private IP address'),
    (re.compile(r'(?<![\d.])\d{12,}(?![\d.])'), 'long numeric id'),
]

# String literals are pure data, so all of one is worth looking at. Backticks
# are included for Go's raw strings, where a path is most likely to sit
# verbatim; the cost is that a `code span` in a comment is read as a literal
# too, which only matters if it looks like content and is undeclared.
STRING_LITERAL = re.compile(
    r"(?P<rawq>r?)'(?P<sq>[^'\n\\]*(?:\\.[^'\n\\]*)*)'"
    r"|(?P<rawqq>r?)\"(?P<dq>[^\"\n\\]*(?:\\.[^\"\n\\]*)*)\""
    r"|`(?P<bt>[^`]*)`")

# Markdown is mostly prose, so whole lines say nothing. Only tokens shaped
# like a path or a file name are data: a backslash-separated path, or anything
# ending in a media extension. Both forms of the leak this exists to stop
# (`<share>\<work>.pdf`) are caught by either half.
MD_BREAK = r'\s`\'"()<>|,、。（）「」'
MD_TOKEN = re.compile(
    r'[^%s]*(?:\\[^%s\\]+)+'
    r'|[^%s]+\.(?:pdf|zip|cbz|rar|jpe?g|png|gif|webp|mp4|mkv|avi|webm|mov'
    r'|wmv|m4v)\b' % (MD_BREAK, MD_BREAK, MD_BREAK),
    re.I,
)


class Policy:
    """What counts as private here: the vocabulary, the denylist, the scopes.

    Carried as one object because every check needs all of it, and threading
    five parameters through each of them was worse.
    """

    def __init__(self, root, args):
        self.root = root
        vocab = abspath(root, args.vocabulary)
        self.vocabulary_known = os.path.exists(vocab)
        self.tokens, self.patterns = load_vocabulary(vocab)
        self.denylist = load_denylist(abspath(root, args.denylist))
        self.data_scope = compile_all(args.data_scope or DEFAULT_DATA_SCOPE)
        scan = args.scan_scope or (
            tuple(args.data_scope or ()) + DEFAULT_SCAN_SCOPE)
        self.scan_scope = compile_all(scan)

    def in_scan_scope(self, path):
        return any(p.search(path) for p in self.scan_scope)

    def in_data_scope(self, path):
        return self.vocabulary_known and \
            any(p.search(path) for p in self.data_scope)

    def known(self, text):
        """Whether every segment of [text] is declared in the vocabulary."""
        if any(p.search(text) for p in self.patterns):
            return True
        segments = [s for s in re.split(r'[\\/]+', text) if s]
        if not segments:
            return True
        return all(s in self.tokens
                   or any(p.fullmatch(s) for p in self.patterns)
                   for s in segments)


def abspath(root, path):
    return path if os.path.isabs(path) else os.path.join(root, path)


def compile_all(patterns):
    return tuple(re.compile(p) for p in patterns)


def repo_root():
    """The repository being checked, or the directory holding this script."""
    done = subprocess.run(['git', 'rev-parse', '--show-toplevel'],
                          capture_output=True, text=True)
    if done.returncode == 0 and done.stdout.strip():
        return done.stdout.strip()
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def strip_comment(line):
    """'#' is a comment only at the start or after a space: it is also a legal
    character in a path segment, and `b#c` is a test case."""
    return re.sub(r'(?:^|\s)#.*$', '', line).strip()


def load_vocabulary(path):
    """Allowed path segments and file names, plus regexes for generated ones."""
    tokens, patterns = set(), []
    if not os.path.exists(path):
        return tokens, patterns
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = strip_comment(line)
            if not line:
                continue
            if line.startswith('~'):
                patterns.append(re.compile(line[1:]))
            else:
                tokens.add(line)
    return tokens, patterns


def load_denylist(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as f:
        return [t for t in (strip_comment(l) for l in f) if t]


def looks_like_content(text, cjk_counts=True):
    """Whether this span is the kind of thing real data hides in.

    [cjk_counts] is false for Markdown, which may be written in a CJK
    language: there, only a path-shaped or media-named token can be data.
    """
    if cjk_counts and CJK.search(text):
        return True
    if MEDIA.search(text):
        return True
    if ESCAPE_NOT_PATH.match(text):
        return False
    return bool(re.search(r'[^\s\\/]\\[^\s\\/]', text))


def literals_of(path, content):
    """Every span in this file that is data rather than prose."""
    if path.endswith('.md'):
        for lineno, line in enumerate(content.split('\n'), 1):
            for m in MD_TOKEN.finditer(line):
                if m.group(0).strip():
                    yield lineno, m.group(0).strip()
        return
    for m in STRING_LITERAL.finditer(content):
        text = next((m.group(g) for g in ('sq', 'dq', 'bt')
                     if m.group(g) is not None), None)
        if not text:
            continue
        if not (m.group('rawq') or m.group('rawqq') or m.group('bt')):
            # Escapes are not path separators: `$e\n$st` is one line of log,
            # not a two-segment path.
            text = re.sub(r'\\(.)', r'\1', text)
        yield content[:m.start()].count('\n') + 1, text


def check_content(path, content, policy):
    problems = []
    for lineno, line in enumerate(content.split('\n'), 1):
        for rx, why in STRUCTURAL:
            m = rx.search(line)
            if m and not policy.known(m.group(0)):
                problems.append((path, lineno, why, m.group(0)))
        for term in policy.denylist:
            if term.lower() in line.lower():
                problems.append((path, lineno, 'known private name', term))

    if policy.in_data_scope(path):
        cjk_counts = not path.endswith('.md')
        for lineno, text in literals_of(path, content):
            if looks_like_content(text, cjk_counts) and not policy.known(text):
                problems.append((path, lineno,
                                 'not in the test vocabulary', text))
    return problems


def git(root, *args):
    return subprocess.run(['git'] + list(args), cwd=root, capture_output=True,
                          text=True, errors='replace').stdout


def check_staged(policy):
    names = git(policy.root, 'diff', '--cached', '--name-only',
                '--diff-filter=ACMR').split('\n')
    problems = []
    for path in filter(None, names):
        if policy.in_scan_scope(path):
            problems += check_content(
                path, git(policy.root, 'show', ':' + path), policy)
    return problems


def check_worktree(policy):
    problems = []
    for path in filter(None, git(policy.root, 'ls-files').split('\n')):
        full = os.path.join(policy.root, path)
        if not policy.in_scan_scope(path) or not os.path.exists(full):
            continue
        with open(full, encoding='utf-8', errors='replace') as f:
            problems += check_content(path, f.read(), policy)
    return problems


def check_message(rev, policy):
    """A commit message carries data too, and is not caught by any file scan."""
    problems = []
    message = git(policy.root, 'log', '-1', '--format=%B', rev)
    for lineno, line in enumerate(message.split('\n'), 1):
        where = rev[:9] + ' (message)'
        for term in policy.denylist:
            if term.lower() in line.lower():
                problems.append((where, lineno, 'known private name', term))
        for rx, why in STRUCTURAL:
            m = rx.search(line)
            if m and not policy.known(m.group(0)):
                problems.append((where, lineno, why, m.group(0)))
        if not policy.vocabulary_known:
            continue
        for m in MD_TOKEN.finditer(line):
            token = m.group(0).strip()
            if looks_like_content(token, False) and not policy.known(token):
                problems.append((where, lineno,
                                 'not in the test vocabulary', token))
    return problems


def check_revisions(revs, policy):
    """Every blob that ever existed shows up as changed in some revision, so
    scanning each revision's own changes covers the whole history once."""
    problems = []
    for rev in revs:
        problems += check_message(rev, policy)
        changed = git(policy.root, 'diff-tree', '-r', '--no-commit-id',
                      '--name-only', '--diff-filter=ACMR', rev).split('\n')
        for path in filter(None, changed):
            if not policy.in_scan_scope(path):
                continue
            content = git(policy.root, 'show', '%s:%s' % (rev, path))
            for p, lineno, why, hit in check_content(path, content, policy):
                problems.append(('%s %s' % (rev[:9], p), lineno, why, hit))
    return problems


def parse_args():
    ap = argparse.ArgumentParser(
        description='Fail on private data reaching this repository.')
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--staged', action='store_true')
    g.add_argument('--worktree', action='store_true')
    g.add_argument('--range')
    g.add_argument('--all-history', action='store_true')
    ap.add_argument('--vocabulary', default=DEFAULT_VOCAB, metavar='PATH')
    ap.add_argument('--denylist', default=DEFAULT_DENYLIST, metavar='PATH')
    ap.add_argument('--data-scope', action='append', metavar='RE')
    ap.add_argument('--scan-scope', action='append', metavar='RE')
    return ap.parse_args()


def report(problems, policy, vocabulary_path):
    print('Private data check failed:\n', file=sys.stderr)
    for path, lineno, why, hit in problems:
        print('  %s:%s: %s: %s' % (path, lineno, why, hit), file=sys.stderr)
    print('\n%d problem(s).\n' % len(problems), file=sys.stderr)
    if not policy.vocabulary_known:
        print('Only the structural checks ran: %s does not exist.'
              % vocabulary_path, file=sys.stderr)
        return
    print('If this is real data, replace it with names from %s.'
          % vocabulary_path, file=sys.stderr)
    print('If it is invented and the check is simply unaware of it, add it to '
          'that file', file=sys.stderr)
    print('-- that is the point: new test data is declared, not assumed.',
          file=sys.stderr)


def main():
    args = parse_args()
    policy = Policy(repo_root(), args)

    if args.staged:
        problems = check_staged(policy)
    elif args.worktree:
        problems = check_worktree(policy)
    else:
        spec = ['--all'] if args.all_history else [args.range]
        revs = [r for r in git(policy.root, 'rev-list', *spec).split('\n') if r]
        problems = check_revisions(revs, policy)

    if not problems:
        return 0
    report(problems, policy, args.vocabulary)
    return 1


if __name__ == '__main__':
    sys.exit(main())
