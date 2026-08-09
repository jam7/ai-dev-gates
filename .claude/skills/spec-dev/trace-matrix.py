#!/usr/bin/env python3
"""Traceability matrix for spec-dev documents (R/S/D/T IDs).

Scans markdown docs for ID definitions (headings like "### S-01: ...") and
references (any other occurrence), then reports coverage holes:
  - R defined but never referenced in spec docs
  - S defined but never referenced in design docs
  - S defined but never referenced from test files (when --code is given)
  - IDs referenced but never defined (typo detection)
  - IDs defined more than once

Doc roles are inferred from filenames: requirements*.md / spec*.md /
design*.md. Files with other names still participate in generic checks.
Stdlib only, Python 3.6+.

Usage:
  trace-matrix.py [--code DIR]... [--matrix] <docs-dir-or-md-file>...

Options:
  --code DIR   also scan source/tests for references (repeatable).
               Files whose path contains "test" count as test files.
  --matrix     print the full ID matrix (markdown table)

Exit codes: 0 = no problems, 1 = coverage problems found, 2 = usage error.
"""

import os
import re
import sys

ID_RE = re.compile(r"\b([RSDT]-\d+)\b")
HEAD_DEF_RE = re.compile(r"^#{1,6}\s+([RSDT]-\d+)\b")


def walk_tree(top, exts):
    """Files under [top], skipping dot-directories. [exts] None means all."""
    found = []
    for root, dirs, names in os.walk(top):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        found.extend(os.path.join(root, name) for name in sorted(names)
                     if exts is None or os.path.splitext(name)[1] in exts)
    return found


def collect(paths, exts=None):
    files = []
    for p in paths:
        if os.path.isdir(p):
            files.extend(walk_tree(p, exts))
        elif os.path.isfile(p):
            files.append(p)
        else:
            sys.stderr.write("error: no such path: %s\n" % p)
            sys.exit(2)
    return files


def doc_role(path):
    base = os.path.basename(path).lower()
    for role in ("requirements", "spec", "design"):
        if base.startswith(role):
            return role
    return "other"


def scan(doc_files, code_files):
    defs = {}    # id -> [(file, line)]
    refs = {}    # id -> [(file, line, kind)]  kind: doc role / 'code' / 'test'
    for path in doc_files:
        role = doc_role(path)
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                lines = f.read().splitlines()
        except OSError as e:
            sys.stderr.write("error: cannot read %s: %s\n" % (path, e))
            sys.exit(2)
        for lineno, line in enumerate(lines, 1):
            m = HEAD_DEF_RE.match(line)
            def_id = m.group(1) if m else None
            for ident in ID_RE.findall(line):
                if ident == def_id:
                    defs.setdefault(ident, []).append((path, lineno))
                    def_id = None  # only the first occurrence is the definition
                else:
                    refs.setdefault(ident, []).append((path, lineno, role))
    for path in code_files:
        kind = "test" if re.search(r"test", path, re.I) else "code"
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                content = f.read().splitlines()
        except OSError:
            continue
        for lineno, line in enumerate(content, 1):
            for ident in ID_RE.findall(line):
                # T-IDs live in test code by convention: the first
                # occurrence in a test file is the test's definition.
                if kind == "test" and ident.startswith("T-") \
                        and ident not in defs:
                    defs.setdefault(ident, []).append((path, lineno))
                else:
                    refs.setdefault(ident, []).append((path, lineno, kind))
    return defs, refs


def id_key(ident):
    return (ident[0], int(ident.split("-")[1]))


def check(defs, refs, have_roles, have_code):
    problems = []

    def referenced_in(ident, kinds):
        return any(r[2] in kinds for r in refs.get(ident, []))

    for ident in sorted(defs, key=id_key):
        locs = defs[ident]
        if len(locs) > 1:
            problems.append("%s: defined %d times (%s)" % (
                ident, len(locs),
                ", ".join("%s:%d" % (f, l) for f, l in locs)))
        kind = ident[0]
        if kind == "R" and "spec" in have_roles \
                and not referenced_in(ident, {"spec"}):
            problems.append("%s: not covered by any spec doc" % ident)
        if kind == "S" and "design" in have_roles \
                and not referenced_in(ident, {"design"}):
            problems.append("%s: not covered by any design doc" % ident)
        if kind == "S" and have_code \
                and not referenced_in(ident, {"test"}):
            problems.append("%s: no test references it" % ident)
    for ident in sorted(refs, key=id_key):
        if ident not in defs:
            first = refs[ident][0]
            problems.append("%s: referenced (%s:%d) but never defined"
                            " - typo or missing section?"
                            % (ident, first[0], first[1]))
    return problems


def print_matrix(defs, refs):
    print("| ID | defined at | referenced from |")
    print("|---|---|---|")
    for ident in sorted(set(defs) | set(refs), key=id_key):
        d = ", ".join("%s:%d" % (f, l) for f, l in defs.get(ident, []))
        seen = []
        for f, l, _k in refs.get(ident, []):
            short = os.path.basename(f)
            if short not in seen:
                seen.append(short)
        print("| %s | %s | %s |" % (ident, d or "(undefined)",
                                    ", ".join(seen) or "(none)"))


def main(argv):
    doc_paths, code_paths, matrix = [], [], False
    i = 1
    while i < len(argv):
        if argv[i] == "--code":
            i += 1
            if i >= len(argv):
                sys.stderr.write("error: --code needs a path\n")
                sys.exit(2)
            code_paths.append(argv[i])
        elif argv[i] == "--matrix":
            matrix = True
        elif argv[i] in ("-h", "--help"):
            sys.stdout.write(__doc__)
            sys.exit(0)
        else:
            doc_paths.append(argv[i])
        i += 1
    if not doc_paths:
        sys.stderr.write(__doc__)
        sys.exit(2)

    doc_files = collect(doc_paths, exts={".md"})
    if not doc_files:
        sys.stderr.write("error: no .md files found in: %s\n"
                         % " ".join(doc_paths))
        sys.exit(2)
    code_files = collect(code_paths) if code_paths else []
    defs, refs = scan(doc_files, code_files)
    have_roles = {doc_role(f) for f in doc_files}
    problems = check(defs, refs, have_roles, bool(code_files))

    counts = {}
    for ident in defs:
        counts[ident[0]] = counts.get(ident[0], 0) + 1
    print("== Definitions ==")
    print("  " + ", ".join("%s: %d" % (k, counts.get(k, 0))
                           for k in "RSDT"))
    if matrix:
        print("\n== Matrix ==")
        print_matrix(defs, refs)
    print("\n== Problems: %d ==" % len(problems))
    for p in problems:
        print("  " + p)
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main(sys.argv)
