#!/usr/bin/env python3
"""Traceability matrix for spec-dev documents (R/S/D/T IDs).

Scans markdown docs for ID definitions (headings like "### S-01: ...") and
references (any other occurrence), then reports coverage holes:
  - R defined but never referenced in spec docs
  - S defined but never referenced in design docs
  - S defined but never referenced from test files (when --code is given)
  - IDs referenced but never defined (typo detection)
  - IDs defined more than once

Retirement: withdrawing or moving an ID out deletes its body (git holds the
history) and leaves one line in a ledger section whose heading contains 退役:
  ## 退役 (番号は再利用しない)
  - R-05: 2026-08-13 撤回 -- ... (ADR-07)
A retired ID is a valid reference target and is exempt from coverage, but a
live heading that claims to realize one is reported, and so is a retired ID
that is still (or again) defined -- the number is never reused.

Two gate checks that used to be done by eye (an ad-hoc one-liner once
reported all 10 sections as missing when 3 were):
  - every section of a kind carries its required subheadings
    (default: S needs 受入条件 and 境界条件・エラー時, R needs 入出力例 and
    境界条件 -- the fields the shipped templates use)
  - no ambiguous wording inside an ID's section, in requirements and spec
    docs (適切に / 必要に応じて / など / 高速に / 柔軟に / 原則として)

Both are declared per feature in <docs-dir>/trace-gate.txt, same philosophy
as tools/cq-baseline.txt: an exception passes only with a written reason.
  require: S = 受入条件, 境界条件・エラー時   what a kind's section needs
  require: R =                               (empty list disables the check)
  words: など, 適切に                         replace the ambiguous-word list
  word: S-03 など                            this word stays here, reason above
  heading: R-02 入出力例                     this section lacks it on purpose

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
HEADING_RE = re.compile(r"(#{1,6})\s")

# The wording gate G1 greps for by hand; trace-gate.txt `words:` replaces it.
AMBIGUOUS_WORDS = ("適切に", "必要に応じて", "など", "高速に", "柔軟に",
                   "原則として")
# What a kind's section must contain, matching the fields the shipped
# templates use; trace-gate.txt `require:` lines override per feature.
DEFAULT_REQUIRED = {
    "S": ("受入条件", "境界条件・エラー時"),
    "R": ("入出力例", "境界条件"),
}
GATE_FILE = "trace-gate.txt"


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
    claims = []  # (defined id, other id on its heading line, file, line)
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
            idents = ID_RE.findall(line)
            for ident in idents:
                if ident == def_id:
                    defs.setdefault(ident, []).append((path, lineno))
                    def_id = None  # only the first occurrence is the definition
                else:
                    refs.setdefault(ident, []).append((path, lineno, role))
            if m:
                # A heading like "S-02: ... (realizes R-05)" is a live
                # structural claim, not a historical mention.
                claims.extend((m.group(1), other, path, lineno)
                              for other in idents if other != m.group(1))
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
    return defs, refs, claims


def collect_retired(doc_files):
    """IDs listed in a retirement-ledger section (a heading containing 退役).
    The entry is one line; the deleted body lives in git, not the document."""
    retired = {}
    for path in doc_files:
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                lines = f.read().splitlines()
        except OSError:
            continue
        in_ledger = False
        for lineno, line in enumerate(lines, 1):
            if HEADING_RE.match(line):
                in_ledger = "退役" in line
                continue
            if in_ledger:
                m = re.match(r"^\s*[-*]\s*([RSDT]-\d+)\b", line)
                if m:
                    retired.setdefault(m.group(1), (path, lineno))
    return retired


def id_key(ident):
    return (ident[0], int(ident.split("-")[1]))


def load_gate(path):
    """Per-feature gate declarations: what to require, what to accept.

    Returns (required, allow, words). [allow] holds (ident, text) pairs from
    `word:` and `heading:` entries -- the reason lives in a comment above
    each, like cq-baseline.txt, and writing the entry is the review."""
    required = dict(DEFAULT_REQUIRED)
    allow = set()
    words = AMBIGUOUS_WORDS
    if not os.path.exists(path):
        return required, allow, words
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = re.sub(r"(?:^|\s)#.*$", "", raw).strip()
            if not line:
                continue
            if line.startswith("require:"):
                kind, _, rest = line[len("require:"):].partition("=")
                required[kind.strip()] = tuple(
                    p.strip() for p in rest.split(",") if p.strip())
            elif line.startswith("words:"):
                words = tuple(w.strip() for w in
                              line[len("words:"):].split(",") if w.strip())
            elif line.startswith(("word:", "heading:")):
                _, _, rest = line.partition(":")
                ident, _, text = rest.strip().partition(" ")
                allow.add((ident, text.strip()))
    return required, allow, words


def id_sections(lines):
    """(ident, first_line, last_line) for every ID-defining heading. A
    section runs until the next heading at the same or a shallower depth."""
    heads = []
    for lineno, line in enumerate(lines, 1):
        m = HEADING_RE.match(line)
        if m:
            d = HEAD_DEF_RE.match(line)
            heads.append((lineno, len(m.group(1)),
                          d.group(1) if d else None))
    sections = []
    for i, (lineno, level, ident) in enumerate(heads):
        if ident is None:
            continue
        end = len(lines)
        for next_line, next_level, _ in heads[i + 1:]:
            if next_level <= level:
                end = next_line - 1
                break
        sections.append((ident, lineno, end))
    return sections


def phrase_re(phrase):
    """A required subheading, in any of the notations real documents use:
    '- 受入条件 (テスト可能な形で):', '**受入条件**', '#### 受入条件'."""
    return re.compile(r"^\s*(?:[-*>]\s*|#{1,6}\s*)*\**\s*" + re.escape(phrase))


def missing_headings(path, lines, sections, required, allow):
    problems = []
    for ident, start, end in sections:
        for phrase in required.get(ident[0], ()):
            if (ident, phrase) in allow:
                continue
            rx = phrase_re(phrase)
            if not any(rx.match(l) for l in lines[start:end]):
                problems.append("%s: section lacks 「%s」 (%s:%d)"
                                % (ident, phrase, path, start))
    return problems


def ambiguous_words(path, lines, sections, words, allow):
    """Ambiguous wording inside an ID's section. Only there: the 用語定義
    section exists to define these words, so it always contains them."""
    problems = []
    for ident, start, end in sections:
        for lineno in range(start, end + 1):
            for word in words:
                if word in lines[lineno - 1] and (ident, word) not in allow:
                    problems.append("%s:%d: ambiguous 「%s」 (%s)"
                                    % (path, lineno, word, ident))
    return problems


def check_gates(doc_files):
    """The two gate checks that used to be manual, per feature directory."""
    problems = []
    configs = {}
    for path in doc_files:
        feature_dir = os.path.dirname(path) or "."
        if feature_dir not in configs:
            configs[feature_dir] = load_gate(
                os.path.join(feature_dir, GATE_FILE))
        required, allow, words = configs[feature_dir]
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                lines = f.read().splitlines()
        except OSError:
            continue
        sections = id_sections(lines)
        problems += missing_headings(path, lines, sections, required, allow)
        if doc_role(path) in ("requirements", "spec"):
            problems += ambiguous_words(path, lines, sections, words, allow)
    return problems


def check_coverage(defs, refs, have_roles, have_code):
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
    return problems


def check_references(refs, defs, retired):
    """A mention must point at something: a definition, or a ledger entry."""
    problems = []
    for ident in sorted(refs, key=id_key):
        if ident not in defs and ident not in retired:
            first = refs[ident][0]
            problems.append("%s: referenced (%s:%d) but never defined"
                            " - typo or missing section?"
                            % (ident, first[0], first[1]))
    return problems


def check_retired(defs, retired, claims):
    """A retired number is never reused, and nothing live builds on it."""
    problems = []
    for ident in sorted(set(defs) & set(retired), key=id_key):
        f, l = retired[ident]
        problems.append("%s: in the retirement ledger (%s:%d) but still "
                        "defined (%s:%d) - the number is never reused"
                        % (ident, f, l, defs[ident][0][0], defs[ident][0][1]))
    for def_id, other, path, lineno in claims:
        if other in retired and def_id not in retired:
            problems.append("%s: its heading claims retired %s (%s:%d)"
                            % (def_id, other, path, lineno))
    return problems


def print_matrix(defs, refs, retired):
    print("| ID | defined at | referenced from |")
    print("|---|---|---|")
    for ident in sorted(set(defs) | set(refs) | set(retired), key=id_key):
        d = ", ".join("%s:%d" % (f, l) for f, l in defs.get(ident, []))
        if not d and ident in retired:
            d = "(retired %s:%d)" % retired[ident]
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
    defs, refs, claims = scan(doc_files, code_files)
    retired = collect_retired(doc_files)
    have_roles = {doc_role(f) for f in doc_files}
    problems = check_coverage(defs, refs, have_roles, bool(code_files))
    problems += check_references(refs, defs, retired)
    problems += check_retired(defs, retired, claims)
    problems += check_gates(doc_files)

    counts = {}
    for ident in defs:
        counts[ident[0]] = counts.get(ident[0], 0) + 1
    print("== Definitions ==")
    print("  " + ", ".join("%s: %d" % (k, counts.get(k, 0))
                           for k in "RSDT"))
    if retired:
        print("  retired: " + ", ".join(sorted(retired, key=id_key)))
    if matrix:
        print("\n== Matrix ==")
        print_matrix(defs, refs, retired)
    print("\n== Problems: %d ==" % len(problems))
    for p in problems:
        print("  " + p)
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main(sys.argv)
