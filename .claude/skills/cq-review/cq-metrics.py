#!/usr/bin/env python3
"""Code quality metrics for brace-style languages (C/C++/Go/Java/JS/Rust etc)
and Python.

Heuristic candidate finder for code review: long functions, deep nesting,
long parameter lists, duplicated code blocks. It intentionally trades parsing
precision for zero dependencies — treat results as review candidates, not
verdicts. Stdlib only, Python 3.6+.

Blocks are counted by brace depth, or by indentation level in Python. Neither
is a parse: a `def` is found by pattern and its body is what is indented under
it, the same way a `{` opens a block elsewhere.

Usage:
  cq-metrics.py [options] <file-or-dir>...

Options:
  --max-func-lines N   flag functions with more than N code lines (default 60;
                       comments and blank lines are not counted)
  --max-nest N         flag nesting deeper than N inside a function (default 4)
  --max-params N       flag parameter lists longer than N (default 5)
  --dup-window N       duplicate block size in significant lines (default 8, 0=off)
  --ext .a,.b          comma-separated extensions for directory scan
  --top N              show at most N findings per category (default 20)
  --csv                print one CSV data line instead of the report:
                       label,files,functions,long_funcs,deep_nest,long_params,dup_groups
                       (for trend tracking: cq-metrics.py --csv --label $(git rev-parse --short HEAD) src/ >> cq-trend.csv)
  --label TEXT         label for the --csv line (e.g. commit hash; default "-")

Exit codes: 0 = ran (findings are informational), 2 = usage/file error.
"""

import os
import re
import sys

DEFAULT_EXTS = (".c", ".h", ".cc", ".hh", ".cpp", ".hpp", ".cxx", ".go",
                ".java", ".js", ".ts", ".rs", ".m", ".mm", ".dart", ".kt",
                ".swift", ".cs", ".py")
# Languages whose blocks are indentation rather than braces.
INDENT_EXTS = (".py",)
CONTROL_KEYWORDS = {"if", "else", "for", "while", "do", "switch", "case",
                    "return", "catch", "struct", "class", "enum", "union",
                    "namespace", "typedef", "using", "extern", "select",
                    "match", "impl", "loop", "unsafe", "synchronized",
                    "import", "package"}
NAME_RE = re.compile(r"([A-Za-z_][\w:~.]*)\s*\($")
GO_FUNC_RE = re.compile(r"^\s*func\s*(?:\([^)]*\)\s*)?([A-Za-z_]\w*)\s*\(")
PY_DEF_RE = re.compile(r"^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)\s*\(")
PY_CLASS_RE = re.compile(r"^\s*class\s+([A-Za-z_]\w*)")
# The receiver is implicit in the brace languages, so it is not counted here
# either: a 5-parameter method should read the same in both.
PY_RECEIVER_RE = re.compile(r"^\s*(?:self|cls)\s*(?:[,:]|$)")

# Import declarations are near-identical between files by their nature: two
# files needing the same five packages name them the same way, in the order the
# formatter chose, and no language lets that list be shared. Reporting it as
# duplication buries the real findings -- a run of eight imports is far more
# common than a run of eight duplicated statements.
# "use" and "using" also begin real statements -- Rust has use_cache(x), C# has
# "using var f = File.Open(p)" and "using (var f = ...)" -- so those two are
# matched only in their declaration form: one dotted name, optionally aliased,
# ending the line. Anything with a call or a second identifier in it is code.
IMPORT_RE = re.compile(
    r"^(?:"
    r"import\b"                              # Java, Kotlin, Swift, Python, JS, Go
    r"|from\s+\S+\s+import\b"                 # Python
    r"|use\s+[\w:{*\\][\w:{}*,\s\\]*;"         # Rust, PHP (PHP separates with \)
    r"|using\s+[\w.:<>]+\s*(?:=\s*[\w.:<>]+\s*)?;"  # C#, C++
    r"|require\s*\(?\s*[\"']"                 # Ruby, Node
    r"|package\s+[\w.]"                       # Go, Java, Kotlin package declaration
    r")")
# Go and Scala group imports in a parenthesised block, and Python wraps long
# ones the same way. Their lines are bare paths or names, so they match nothing
# on their own and the block has to be tracked.
IMPORT_BLOCK_OPEN_RE = re.compile(
    r"^(?:import\s*\(|from\s+\S+\s+import\s*\()\s*$")
IMPORT_BLOCK_CLOSE_RE = re.compile(r"^\)")


def significant_lines(lines):
    """The lines worth comparing for duplication, with their numbers.

    Drops blanks, preprocessor directives, punctuation-only lines and import
    declarations. What is left is code that a person wrote and could have
    written differently.
    """
    out = []
    in_import_block = False
    for lineno, line in enumerate(lines, 1):
        s = re.sub(r"\s+", " ", line.strip())
        if in_import_block:
            if IMPORT_BLOCK_CLOSE_RE.match(s):
                in_import_block = False
            continue
        if IMPORT_BLOCK_OPEN_RE.match(s):
            in_import_block = True
            continue
        if not s or len(s) <= 3 or s.startswith("#"):
            continue
        if re.fullmatch(r"[{}();,]*", s) or IMPORT_RE.match(s):
            continue
        out.append((lineno, s))
    return out


# What ends each state. These are the only characters strip_code has to look
# at: everything between them is a run of one kind of text, handled in one
# piece. The regexes are not parsing anything -- they are a way to say "skip
# to the next interesting character" that runs in C rather than in a Python
# loop, which is most of why the scan is fast.

# In ordinary code, a comment or a literal may open.
OUTSIDE_RE = re.compile(r"[#\"'`]|//|/\*")
# In a literal, three things matter: an escape (the next character cannot
# close the literal), the matching quote, and a newline -- which is emitted as
# itself so line numbers hold, and does not end the literal, because a string
# with an unescaped newline is a broken file rather than a closed string.
LITERAL_STOP = {q: re.compile(r"[\\%s\n]" % re.escape(q)) for q in ('"', "'")}
LITERAL_STOP["`"] = re.compile(r"[`\n]")   # no escapes in a raw string
NON_NEWLINE_RE = re.compile(r"[^\n]")


def blank_run(chunk):
    """The same text with everything but newlines turned into spaces."""
    return NON_NEWLINE_RE.sub(" ", chunk)


# The three step functions below each answer the same question for one state:
# given this character and the next, what state comes next, how many
# characters did that take, and what stands in their place? Emitting a
# replacement of the same width is what keeps line numbers and columns intact.

def step_outside(c, nxt):
    """A step in plain code, where a comment or a literal may open."""
    if c == "#":
        # A comment in Python and a directive in C, and both are dropped by
        # every consumer below -- but leaving it alone meant an apostrophe in
        # a Python comment (`# Go's raw strings`) opening a string that
        # swallowed the rest of the file.
        return "line", 1, " "
    if c == "/" and nxt == "/":
        return "line", 2, "  "
    if c == "/" and nxt == "*":
        return "block", 2, "  "
    if c in ('"', "'", "`"):
        return c, 1, c
    return None, 1, c


def step_comment(state, c, nxt):
    """A step inside a comment. Newlines are kept, everything else is space."""
    if state == "line":
        return (None, 1, c) if c == "\n" else ("line", 1, " ")
    if c == "*" and nxt == "/":
        return None, 2, "  "
    return "block", 1, (c if c == "\n" else " ")


def step_literal(state, c, nxt, keep_strings):
    """A step inside a string or character literal."""
    if c == "\\" and state != "`":
        # An escape is two characters, and the second cannot close the
        # literal -- `'\''` is one quote, not an empty string.
        escaped = nxt if keep_strings and nxt and nxt != "\n" else " "
        return state, 2, (c if keep_strings else " ") + escaped
    if c == state:
        return None, 1, c
    if c == "\n":
        return state, 1, c
    return state, 1, (c if keep_strings else " ")


# How to read strip_code below.
#
# The loop walks states, not characters. Whatever state it is in, everything
# up to the thing that ends that state is one uninteresting run -- ordinary
# code, comment text, string contents -- so the run is emitted in one piece
# and only the character that ended it is examined. Source is overwhelmingly
# ordinary characters, so this is where the time is: skipping the run with a
# regex search instead of a per-character Python loop makes the whole tool
# about twice as fast.
#
# Every branch has the same three parts, and reads best if you look for them:
#
#   1. find where the current state ends,
#   2. emit the run -- always the same width as what it replaces, with
#      newlines kept, so that columns and line numbers still match the
#      original file,
#   3. hand the character that ended it to the step function that owns that
#      state, which says what comes next.
#
# The `break` in each branch is the unterminated case: a file that ends inside
# a comment or a string. There is no terminator to step over, so the run is
# emitted and the scan is done.

def strip_code(text, keep_strings=False):
    """Blank out comments (and, unless keep_strings, string/char literal
    contents), preserving line structure so line numbers and braces stay
    meaningful."""
    out = []
    i, n = 0, len(text)
    state = None  # None, 'line', 'block', '"', "'", '`'
    while i < n:
        if state is None:
            # Ordinary code, copied through untouched.
            m = OUTSIDE_RE.search(text, i)
            if m is None:
                out.append(text[i:])
                break
            out.append(text[i:m.start()])
            i = m.start()
            state, used, emit = step_outside(text[i], text[i + 1:i + 2])
        elif state == "line":
            # To the end of the line. No newline can be inside the run, so
            # blanking it is a plain repeat; the newline itself is emitted by
            # step_comment, which also ends the state.
            stop = text.find("\n", i)
            if stop < 0:
                out.append(" " * (n - i))
                break
            out.append(" " * (stop - i))
            i = stop
            state, used, emit = step_comment("line", "\n", "")
        elif state == "block":
            # To the closing `*/`. The run may span lines, so blank_run keeps
            # the newlines in it.
            stop = text.find("*/", i)
            if stop < 0:
                out.append(blank_run(text[i:]))
                break
            out.append(blank_run(text[i:stop]))
            i = stop
            state, used, emit = step_comment("block", "*", "/")
        else:
            # To the next escape, closing quote or newline -- none of which
            # can appear inside the run, so it needs no blank_run.
            m = LITERAL_STOP[state].search(text, i)
            stop = n if m is None else m.start()
            chunk = text[i:stop]
            out.append(chunk if keep_strings else " " * len(chunk))
            if m is None:
                break
            i = stop
            state, used, emit = step_literal(state, text[i],
                                             text[i + 1:i + 2], keep_strings)
        out.append(emit)
        i += used
    return "".join(out)


def split_params(group):
    """Count parameters in the text between the outer parens."""
    group = group.strip()
    if not group or group == "void":
        return 0
    depth = 0
    count = 1
    for c in group:
        if c in "(<[{":
            depth += 1
        elif c in ")>]}":
            depth -= 1
        elif c == "," and depth == 0:
            count += 1
    return count


def first_paren_group(header):
    """Return contents of the first balanced (...) group, or None."""
    start = header.find("(")
    if start < 0:
        return None
    depth = 0
    for j in range(start, len(header)):
        if header[j] == "(":
            depth += 1
        elif header[j] == ")":
            depth -= 1
            if depth == 0:
                return header[start + 1:j]
    return None


def looks_like_function(header):
    header = header.strip()
    if not header or "(" not in header:
        return False
    group = first_paren_group(header)
    if group is None:
        return False
    first_word = re.match(r"[A-Za-z_#]\w*", header)
    if first_word and first_word.group(0) in CONTROL_KEYWORDS:
        return False
    if first_word and first_word.group(0) == "#":  # preprocessor
        return False
    # 'foo = {...}' initializers and lambda assignments: skip.
    before_paren = header[:header.find("(")]
    if "=" in before_paren:
        return False
    # Header should end right after the param group modulo trailing
    # qualifiers (const, noexcept, override, -> T, throws, initializer list).
    return True


def function_name(header):
    m = GO_FUNC_RE.match(header)
    if m:  # Go: skip the receiver so methods report their real name
        return m.group(1)
    before = header[:header.find("(") + 1]
    m = NAME_RE.search(before.strip())
    return m.group(1) if m else "<anon>"


def param_group(header):
    """Return the parameter (...) contents; for Go methods, the group after
    the method name rather than the receiver."""
    m = GO_FUNC_RE.match(header)
    if m:
        rest = header[m.end() - 1:]
        return first_paren_group(rest)
    return first_paren_group(header)


def indent_of(line):
    expanded = line.expandtabs(8)
    return len(expanded) - len(expanded.lstrip())


def bracket_balance(text):
    """How many brackets this line leaves open. Strings are already blank."""
    return (text.count("(") + text.count("[") + text.count("{")
            - text.count(")") - text.count("]") - text.count("}"))


def py_params(header):
    """Parameter count for a def header, without the implicit receiver."""
    group = first_paren_group(header)
    if group is None:
        return 0
    count = split_params(group)
    if count and PY_RECEIVER_RE.match(group):
        count -= 1
    return count


def close_python(func, functions):
    func["end"] = func["last"]
    functions.append(func)


def indent_level(levels, col):
    """How deep this column is, updating the stack of columns still open.

    Only a column deeper than the one before it opens a level, so a signature
    wrapped four spaces further in reads the same as one that is not.
    """
    while len(levels) > 1 and col < levels[-1]:
        levels.pop()
    if not levels or col > levels[-1]:
        levels.append(col)
    return len(levels) - 1


def open_python(name, scopes, lineno, position):
    """A function record. [position] is its (column, level)."""
    col, level = position
    return {"name": ".".join([s[1] for s in scopes] + [name]),
            "line": lineno, "indent": col, "level": level,
            "params": 0, "max_depth": 0, "last": lineno}


def absorb_continuation(header, stripped, opened):
    """Add a continuation line to a def header being collected across lines.

    Returns the header still wanting more, or "" once the parameters have been
    counted from it.
    """
    if not header:
        return header
    header += " " + stripped
    if bracket_balance(header) > 0:
        return header
    opened[-1]["params"] = py_params(header)
    return ""


def deepen(opened, level, lineno):
    """Record that every open function reached [level] on this line."""
    for func in opened:
        func["last"] = lineno
        if level - func["level"] - 1 > func["max_depth"]:
            func["max_depth"] = level - func["level"] - 1


def analyze_python(lines):
    """Functions in an indentation-based file.

    An indentation column that is deeper than the one before it opens a block,
    exactly as `{` does elsewhere, so the depth reported means the same thing
    in both. Lines continuing an unclosed bracket or a backslash are laid out
    for readability rather than nested, and are skipped.
    """
    functions, opened, scopes, levels = [], [], [], []
    header, pending, cont = "", 0, False

    for lineno, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped:
            continue
        if pending > 0 or cont:
            header = absorb_continuation(header, stripped, opened)
            for func in opened:
                func["last"] = lineno
            pending += bracket_balance(stripped)
            cont = stripped.endswith("\\")
            continue

        col = indent_of(line)
        level = indent_level(levels, col)
        while opened and col <= opened[-1]["indent"]:
            close_python(opened.pop(), functions)
        while scopes and col <= scopes[-1][0]:
            scopes.pop()
        pending = bracket_balance(stripped)
        cont = stripped.endswith("\\")

        found = PY_DEF_RE.match(line)
        if found:
            opened.append(open_python(found.group(1), scopes, lineno,
                                      (col, level)))
            scopes.append((col, found.group(1)))
            header = stripped
            if pending <= 0:
                opened[-1]["params"] = py_params(header)
                header = ""
            continue

        klass = PY_CLASS_RE.match(line)
        if klass:
            scopes.append((col, klass.group(1)))
            continue
        deepen(opened, level, lineno)
    for func in opened:
        close_python(func, functions)
    return functions


def analyze_file(path, opts, dup_index):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            raw = f.read()
    except OSError as e:
        sys.stderr.write("error: cannot read %s: %s\n" % (path, e))
        return None
    lines = strip_code(raw).splitlines()
    if os.path.splitext(path)[1] in INDENT_EXTS:
        functions = analyze_python(lines)
    else:
        functions = analyze_braces(lines)
    for func in functions:
        func["loc"] = code_lines(lines, func["line"], func["end"])
    add_duplicates(path, raw, opts, dup_index)
    return functions


def code_lines(lines, start, end):
    """How many lines of the function are code.

    Comments are already blank at this point, so what is left to skip is
    blank lines -- which is also what a doc comment leaves behind once its
    text is gone. Counting the span instead would mean that explaining a
    function makes it "too long", and a measurement that argues against
    writing the explanation is worse than no measurement.
    """
    return sum(1 for line in lines[start - 1:end] if line.strip())


def add_duplicates(path, raw, opts, dup_index):
    """Record every window of significant lines, for cross-file comparison."""
    if opts["dup_window"] <= 0:
        return
    # Strings are kept: blanking them would make distinct lines look identical.
    sig = significant_lines(strip_code(raw, keep_strings=True).splitlines())
    w = opts["dup_window"]
    for k in range(len(sig) - w + 1):
        key = "\n".join(s for _, s in sig[k:k + w])
        dup_index.setdefault(key, []).append((path, sig[k][0]))


def open_brace(func, depth, header, lineno):
    """Handle a `{`. [header] is (text, first line) of what preceded it.

    Returns (func, depth). A brace only starts a function when none is open:
    the inner braces of one are its body, not another declaration.
    """
    header_buf, header_line = header
    if func is None and looks_like_function(header_buf):
        func = {
            "name": function_name(header_buf),
            "line": header_line or lineno,
            "params": split_params(param_group(header_buf) or ""),
            "entry_depth": depth,
            "max_depth": 0,
        }
    depth += 1
    if func is not None:
        rel = depth - func["entry_depth"] - 1
        if rel > func["max_depth"]:
            func["max_depth"] = rel
    return func, depth


def close_brace(func, depth, functions, lineno):
    """Handle a `}`. Returns (func, depth); func is None once it closed."""
    depth = max(0, depth - 1)
    if func is not None and depth == func["entry_depth"]:
        func["end"] = lineno
        functions.append(func)
        func = None
    return func, depth


def analyze_braces(lines):
    """Functions in a brace-delimited file."""
    functions = []
    depth = 0
    header_buf = ""
    header_line = None
    func = None  # dict while inside a function

    for lineno, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            # Blank line or preprocessor directive: a function header never
            # spans these, and #include/#define braces would corrupt depth.
            header_buf, header_line = "", None
            continue
        for c in line:
            if c == "{":
                func, depth = open_brace(func, depth,
                                         (header_buf, header_line), lineno)
                header_buf, header_line = "", None
            elif c == "}":
                func, depth = close_brace(func, depth, functions, lineno)
                header_buf, header_line = "", None
            elif c == ";":
                header_buf, header_line = "", None
            else:
                if not header_buf.strip() and not c.isspace():
                    header_line = lineno
                header_buf += c
        header_buf += " "
    return functions


def walk_tree(top, exts):
    """Matching files under [top]. Dot-directories are skipped, so a scan of a
    project does not wander into .git or .claude."""
    found = []
    for root, dirs, names in os.walk(top):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        found.extend(os.path.join(root, name) for name in sorted(names)
                     if os.path.splitext(name)[1] in exts)
    return found


def collect_files(paths, exts):
    """The files to measure. A path given explicitly is taken as given; only a
    directory scan filters by extension."""
    files = []
    for p in paths:
        if os.path.isdir(p):
            files.extend(walk_tree(p, exts))
        elif os.path.isfile(p):
            files.append(p)
        else:
            sys.stderr.write("error: no such file or directory: %s\n" % p)
            sys.exit(2)
    return files


def report(title, rows, top):
    print("== %s: %d ==" % (title, len(rows)))
    for row in rows[:top]:
        print("  " + row)
    if len(rows) > top:
        print("  ... and %d more (raise --top to see all)" % (len(rows) - top))
    print()


INT_OPTS = ("--max-func-lines", "--max-nest", "--max-params",
            "--dup-window", "--top")


def option_value(argv, i, name, what="a value"):
    """The value after argv[i], or exit if the option was given without one."""
    if i + 1 >= len(argv):
        sys.stderr.write("error: %s needs %s\n" % (name, what))
        sys.exit(2)
    return argv[i + 1]


def parse_args(argv):
    """Returns (opts, paths). Exits on a malformed option."""
    opts = {"max_func_lines": 60, "max_nest": 4, "max_params": 5,
            "dup_window": 8, "top": 20, "ext": DEFAULT_EXTS,
            "csv": False, "label": "-"}
    paths = []
    i = 1
    while i < len(argv):
        a = argv[i]
        if a in INT_OPTS:
            try:
                opts[a[2:].replace("-", "_")] = int(
                    option_value(argv, i, a, "an integer"))
            except ValueError:
                sys.stderr.write("error: %s needs an integer\n" % a)
                sys.exit(2)
            i += 1
        elif a == "--csv":
            opts["csv"] = True
        elif a == "--label":
            opts["label"] = option_value(argv, i, a)
            i += 1
        elif a == "--ext":
            opts["ext"] = tuple(
                e if e.startswith(".") else "." + e
                for e in option_value(argv, i, a).split(","))
            i += 1
        elif a in ("-h", "--help"):
            sys.stdout.write(__doc__)
            sys.exit(0)
        else:
            paths.append(a)
        i += 1
    if not paths:
        sys.stderr.write(__doc__)
        sys.exit(2)
    return opts, paths


def group_duplicates(dup_index, window):
    """Windows that appear in more than one place, longest run first.

    A block duplicated over N lines produces N - window + 1 overlapping
    windows, all shifted by one; they are one finding, so a run of them is
    collapsed and its extent counted.
    """
    groups = []
    last_locs = None
    for key in sorted(dup_index, key=lambda k: (dup_index[k][0], k)):
        locs = dup_index[key]
        if len(locs) < 2:
            continue
        shifted = last_locs is not None and len(locs) == len(last_locs) and \
            all(a == b and y == x + 1
                for (a, x), (b, y) in zip(last_locs, locs))
        last_locs = locs
        if shifted:
            groups[-1]["extent"] += 1
        else:
            groups.append({"locs": locs, "extent": window})
    groups.sort(key=lambda g: (-len(g["locs"]), -g["extent"]))
    return groups


def main(argv):
    opts, paths = parse_args(argv)
    files = collect_files(paths, opts["ext"])
    if not files:
        sys.stderr.write("error: no source files matched %s\n"
                         % ",".join(opts["ext"]))
        sys.exit(2)

    all_funcs = []
    dup_index = {}
    for path in files:
        funcs = analyze_file(path, opts, dup_index)
        if funcs is not None:
            for f in funcs:
                f["file"] = path
            all_funcs.extend(funcs)

    long_funcs = sorted((f for f in all_funcs
                         if f["loc"] > opts["max_func_lines"]),
                        key=lambda f: -f["loc"])
    deep = sorted((f for f in all_funcs if f["max_depth"] > opts["max_nest"]),
                  key=lambda f: -f["max_depth"])
    many_params = sorted((f for f in all_funcs
                          if f["params"] > opts["max_params"]),
                         key=lambda f: -f["params"])

    dup_groups = group_duplicates(dup_index, opts["dup_window"])

    if opts["csv"]:
        print("%s,%d,%d,%d,%d,%d,%d" % (
            opts["label"].replace(",", "_"), len(files), len(all_funcs),
            len(long_funcs), len(deep), len(many_params), len(dup_groups)))
        return

    report("Long functions (> %d code lines)" % opts["max_func_lines"],
           ["%s:%d  %s()  %d code lines" % (f["file"], f["line"], f["name"],
                                       f["loc"]) for f in long_funcs],
           opts["top"])
    report("Deep nesting (> %d levels)" % opts["max_nest"],
           ["%s:%d  %s()  depth %d" % (f["file"], f["line"], f["name"],
                                       f["max_depth"]) for f in deep],
           opts["top"])
    report("Long parameter lists (> %d params)" % opts["max_params"],
           ["%s:%d  %s()  %d params" % (f["file"], f["line"], f["name"],
                                        f["params"]) for f in many_params],
           opts["top"])
    if opts["dup_window"] > 0:
        report("Duplicated blocks (>= %d significant lines)"
               % opts["dup_window"],
               ["~%d lines x %d sites: %s" % (
                   g["extent"], len(g["locs"]),
                   ", ".join("%s:%d" % loc for loc in g["locs"][:6]))
                for g in dup_groups],
               opts["top"])
    print("== Summary ==")
    print("  files: %d, functions: %d, flagged: long=%d deep=%d params=%d dup-groups=%d"
          % (len(files), len(all_funcs), len(long_funcs), len(deep),
             len(many_params), len(dup_groups)))


if __name__ == "__main__":
    main(sys.argv)
