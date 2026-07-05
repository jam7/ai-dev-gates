#!/usr/bin/env python3
"""Find invisible coupling from git history (co-change analysis).

Two files that repeatedly change in the same commit while living far
apart (different directory, different name) are a strong signal of
hidden coupling: shared assumptions, duplicated knowledge, or implicit
protocols that no type system or include graph will reveal.

Stdlib only, Python 3.6+. Read-only: runs `git log` and never modifies
the repository.

Usage:
  git-cochange.py [options] [REPO]

Options:
  --commits N        analyze the last N commits (default 3000)
  --since DATE       analyze commits since DATE (e.g. "1 year ago");
                     overrides the --commits default cap
  --path P           limit to a subtree (repeatable; git pathspec)
  --exclude GLOB     drop files matching GLOB (repeatable, fnmatch)
  --max-files N      skip commits touching more than N files (default 30;
                     bulk reformats/renames would flood every pair)
  --min-support N    minimum co-change count to report (default 3)
  --min-conf X       minimum confidence to report (default 0.5)
  --include-near     also report pairs in the same directory or with the
                     same stem (foo.h/foo.cpp); excluded by default
  --include-deleted  also report pairs where a file no longer exists
  --top N            show at most N pairs (default 30; --csv is never capped)
  --csv              CSV output: support,confidence,file_a,file_b
  --fail-over N      exit 1 if more than N pairs are reported (CI gate)

Definitions:
  support    = number of commits changing both files
  confidence = max(support/commits(A), support/commits(B))

Exit codes: 0 = ok, 1 = --fail-over exceeded, 2 = usage/git error.
"""

import fnmatch
import os
import subprocess
import sys
from itertools import combinations

MARK = "\x01"


def parse_args(argv):
    opts = {"commits": 3000, "since": None, "paths": [], "excludes": [],
            "max_files": 30, "min_support": 3, "min_conf": 0.5,
            "include_near": False, "include_deleted": False,
            "top": 30, "csv": False, "fail_over": None, "repo": "."}
    i = 1
    while i < len(argv):
        a = argv[i]

        def val():
            nonlocal i
            i += 1
            if i >= len(argv):
                sys.stderr.write("error: %s needs a value\n" % a)
                sys.exit(2)
            return argv[i]

        if a == "--commits":
            opts["commits"] = int(val())
        elif a == "--since":
            opts["since"] = val()
        elif a == "--path":
            opts["paths"].append(val())
        elif a == "--exclude":
            opts["excludes"].append(val())
        elif a == "--max-files":
            opts["max_files"] = int(val())
        elif a == "--min-support":
            opts["min_support"] = int(val())
        elif a == "--min-conf":
            opts["min_conf"] = float(val())
        elif a == "--top":
            opts["top"] = int(val())
        elif a == "--fail-over":
            opts["fail_over"] = int(val())
        elif a == "--include-near":
            opts["include_near"] = True
        elif a == "--include-deleted":
            opts["include_deleted"] = True
        elif a == "--csv":
            opts["csv"] = True
        elif a in ("-h", "--help"):
            sys.stdout.write(__doc__)
            sys.exit(0)
        elif a.startswith("-"):
            sys.stderr.write("error: unknown option %s\n" % a)
            sys.exit(2)
        else:
            opts["repo"] = a
        i += 1
    return opts


def git_log_file_sets(opts):
    """Yield one set of changed paths per (non-merge) commit."""
    cmd = ["git", "-C", opts["repo"], "log", "--no-merges", "--name-only",
           "--pretty=format:%s%%H" % MARK]
    if opts["since"]:
        cmd.append("--since=%s" % opts["since"])
    else:
        cmd.append("-n%d" % opts["commits"])
    if opts["paths"]:
        cmd.append("--")
        cmd.extend(opts["paths"])
    try:
        out = subprocess.run(cmd, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
    except OSError as e:
        sys.stderr.write("error: cannot run git: %s\n" % e)
        sys.exit(2)
    if out.returncode != 0:
        sys.stderr.write("error: git log failed: %s\n"
                         % out.stderr.decode("utf-8", "replace").strip())
        sys.exit(2)
    files = set()
    started = False
    for line in out.stdout.decode("utf-8", "replace").splitlines():
        if line.startswith(MARK):
            if started:
                yield files
            files = set()
            started = True
        elif line.strip():
            files.add(line.strip())
    if started:
        yield files


def stem(path):
    return os.path.splitext(os.path.basename(path))[0]


def is_near(a, b):
    return os.path.dirname(a) == os.path.dirname(b) or stem(a) == stem(b)


def collect_pairs(opts):
    file_count = {}   # path -> commits touching it
    pair_count = {}   # (a, b) sorted tuple -> co-change count
    commits_used = 0
    commits_skipped = 0
    for files in git_log_file_sets(opts):
        files = {f for f in files
                 if not any(fnmatch.fnmatch(f, g) for g in opts["excludes"])}
        if not files:
            continue
        if len(files) > opts["max_files"]:
            commits_skipped += 1
            continue
        commits_used += 1
        for f in files:
            file_count[f] = file_count.get(f, 0) + 1
        for a, b in combinations(sorted(files), 2):
            pair_count[(a, b)] = pair_count.get((a, b), 0) + 1
    return file_count, pair_count, commits_used, commits_skipped


def main(argv):
    opts = parse_args(argv)
    file_count, pair_count, used, skipped = collect_pairs(opts)

    results = []
    for (a, b), support in pair_count.items():
        if support < opts["min_support"]:
            continue
        if not opts["include_near"] and is_near(a, b):
            continue
        if not opts["include_deleted"]:
            if not (os.path.exists(os.path.join(opts["repo"], a))
                    and os.path.exists(os.path.join(opts["repo"], b))):
                continue
        conf = max(support / file_count[a], support / file_count[b])
        if conf < opts["min_conf"]:
            continue
        results.append((conf, support, a, b))
    results.sort(key=lambda r: (-r[0], -r[1], r[2], r[3]))

    if opts["csv"]:
        print("support,confidence,file_a,file_b")
        for conf, support, a, b in results:
            print("%d,%.2f,%s,%s" % (support, conf, a, b))
    else:
        print("== Co-change pairs (support >= %d, confidence >= %.2f)"
              ": %d ==" % (opts["min_support"], opts["min_conf"],
                           len(results)))
        for conf, support, a, b in results[:opts["top"]]:
            print("  %3dx  conf %.2f  %s(%d)  <->  %s(%d)"
                  % (support, conf, a, file_count[a], b, file_count[b]))
        if len(results) > opts["top"]:
            print("  ... and %d more (raise --top to see all)"
                  % (len(results) - opts["top"]))
        print("== Summary ==")
        print("  commits analyzed: %d (skipped %d bulk commits"
              " > %d files), files: %d, pairs reported: %d"
              % (used, skipped, opts["max_files"], len(file_count),
                 len(results)))
    if opts["fail_over"] is not None and len(results) > opts["fail_over"]:
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv)
