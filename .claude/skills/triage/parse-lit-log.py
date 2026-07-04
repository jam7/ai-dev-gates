#!/usr/bin/env python3
"""Parse LLVM lit test logs: extract failures, diff runs, manage baselines.

Works on any log containing llvm-lit output (make check-llvm, check-clang,
ninja check-*, or a raw llvm-lit run). Stdlib only, Python 3.6+.

Usage:
  parse-lit-log.py summary <log>...            # counts + failing tests per log
  parse-lit-log.py fails <log>...              # machine-readable "CODE: name" lines
  parse-lit-log.py diff <old-log> <new-log>    # NEW / FIXED / STILL failing
  parse-lit-log.py detail <log> [pattern]...   # print failure detail blocks
  parse-lit-log.py save <log> <baseline>       # save failures as baseline file
  parse-lit-log.py check <log> <baseline>      # compare vs baseline (exit 1 if new)

'-' can be used instead of a log path to read stdin.
Exit codes: 0 = ok, 1 = new failures found (diff/check), 2 = usage/file error.
"""

import re
import sys

BAD_CODES = ("FAIL", "XPASS", "UNRESOLVED", "TIMEOUT", "ERROR")

RESULT_RE = re.compile(
    r"^(FAIL|XPASS|UNRESOLVED|TIMEOUT|ERROR): (\S.*?)(?: \(\d+ of \d+\))?\s*$"
)
DETAIL_START_RE = re.compile(r"^\*{4,} TEST '(.+)' (?:FAILED|TIMED OUT) \*{4,}\s*$")
DETAIL_END_RE = re.compile(r"^\*{20,}\s*$")
SUMMARY_KEY_RE = re.compile(
    r"^\s{2}(Skipped|Unsupported|Passed|Expectedly Failed|Failed"
    r"|Unexpectedly Passed|Unresolved|Timed Out|Errors?)\s*:\s*(\d+)"
)
TOTAL_RE = re.compile(r"^Total Discovered Tests:\s*(\d+)")
TIME_RE = re.compile(r"^Testing Time:\s*(.+)$")


def read_lines(path):
    if path == "-":
        return sys.stdin.read().splitlines()
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read().splitlines()
    except OSError as e:
        sys.stderr.write("error: cannot read %s: %s\n" % (path, e))
        sys.exit(2)


def parse_log(path):
    """Return dict with failures, details, and summary blocks."""
    lines = read_lines(path)
    failures = {}  # name -> code (first occurrence wins)
    details = {}   # name -> list of lines
    summaries = []
    cur_summary = None
    detail_name = None
    detail_buf = []

    for line in lines:
        if detail_name is not None:
            if DETAIL_END_RE.match(line):
                details[detail_name] = detail_buf
                detail_name, detail_buf = None, []
            else:
                detail_buf.append(line)
            continue

        m = DETAIL_START_RE.match(line)
        if m:
            detail_name = m.group(1)
            detail_buf = []
            continue

        m = RESULT_RE.match(line)
        if m:
            code, name = m.group(1), m.group(2)
            failures.setdefault(name, code)
            continue

        m = TIME_RE.match(line)
        if m:
            cur_summary = {"Testing Time": m.group(1)}
            summaries.append(cur_summary)
            continue
        if cur_summary is not None:
            m = TOTAL_RE.match(line)
            if m:
                cur_summary["Total"] = int(m.group(1))
                continue
            m = SUMMARY_KEY_RE.match(line)
            if m:
                cur_summary[m.group(1)] = int(m.group(2))
                continue
            if line.strip() and not line.startswith(" "):
                cur_summary = None  # summary block ended

    if detail_name is not None:  # unterminated block (truncated log)
        details[detail_name] = detail_buf
    return {"failures": failures, "details": details, "summaries": summaries}


def fail_lines(parsed):
    return ["%s: %s" % (code, name)
            for name, code in sorted(parsed["failures"].items())]


def cmd_summary(paths):
    for path in paths:
        p = parse_log(path)
        print("== %s ==" % path)
        if not p["summaries"]:
            print("  (no lit summary block found)")
        for s in p["summaries"]:
            keys = ["Testing Time", "Total", "Passed", "Expectedly Failed",
                    "Skipped", "Unsupported", "Failed", "Unexpectedly Passed",
                    "Unresolved", "Timed Out"]
            parts = ["%s=%s" % (k, s[k]) for k in keys if k in s]
            print("  " + ", ".join(parts))
        if p["failures"]:
            print("  failing tests (%d):" % len(p["failures"]))
            for line in fail_lines(p):
                print("    " + line)
        else:
            print("  failing tests: none")
        print()


def cmd_fails(paths):
    seen = set()
    for path in paths:
        for line in fail_lines(parse_log(path)):
            if line not in seen:
                seen.add(line)
                print(line)


def load_baseline(path):
    names = {}
    for raw in read_lines(path):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^(%s): (.+)$" % "|".join(BAD_CODES), line)
        if m:
            names[m.group(2)] = m.group(1)
        else:
            names[line] = "FAIL"
    return names


def print_delta(old_names, new_names, old_label, new_label):
    new_only = sorted(set(new_names) - set(old_names))
    fixed = sorted(set(old_names) - set(new_names))
    still = sorted(set(old_names) & set(new_names))
    print("baseline/old: %s (%d failing)" % (old_label, len(old_names)))
    print("new:          %s (%d failing)" % (new_label, len(new_names)))
    print()
    print("NEW failures (%d):" % len(new_only))
    for n in new_only:
        print("  %s: %s" % (new_names[n], n))
    print("FIXED (%d):" % len(fixed))
    for n in fixed:
        print("  %s" % n)
    print("STILL failing (%d):" % len(still))
    for n in still:
        print("  %s: %s" % (new_names[n], n))
    return 1 if new_only else 0


def cmd_diff(old_path, new_path):
    old = parse_log(old_path)["failures"]
    new = parse_log(new_path)["failures"]
    sys.exit(print_delta(old, new, old_path, new_path))


def cmd_detail(path, patterns):
    p = parse_log(path)
    names = sorted(p["details"])
    if patterns:
        names = [n for n in names if any(pat in n for pat in patterns)]
    if not names:
        print("no matching failure detail blocks in %s" % path)
        return
    for n in names:
        print("******************** TEST '%s' ********************" % n)
        for line in p["details"][n]:
            print(line)
        print()


def cmd_save(log_path, baseline_path):
    p = parse_log(log_path)
    lines = fail_lines(p)
    try:
        with open(baseline_path, "w", encoding="utf-8") as f:
            f.write("# lit failure baseline generated from: %s\n" % log_path)
            f.write("# format: CODE: Suite :: path/to/test\n")
            for line in lines:
                f.write(line + "\n")
    except OSError as e:
        sys.stderr.write("error: cannot write %s: %s\n" % (baseline_path, e))
        sys.exit(2)
    print("saved %d failing tests to %s" % (len(lines), baseline_path))


def cmd_check(log_path, baseline_path):
    base = load_baseline(baseline_path)
    new = parse_log(log_path)["failures"]
    sys.exit(print_delta(base, new, baseline_path, log_path))


def main(argv):
    if len(argv) < 2:
        sys.stderr.write(__doc__)
        sys.exit(2)
    cmd, args = argv[1], argv[2:]
    if cmd == "summary" and args:
        cmd_summary(args)
    elif cmd == "fails" and args:
        cmd_fails(args)
    elif cmd == "diff" and len(args) == 2:
        cmd_diff(args[0], args[1])
    elif cmd == "detail" and args:
        cmd_detail(args[0], args[1:])
    elif cmd == "save" and len(args) == 2:
        cmd_save(args[0], args[1])
    elif cmd == "check" and len(args) == 2:
        cmd_check(args[0], args[1])
    else:
        sys.stderr.write(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main(sys.argv)
