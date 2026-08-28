#!/bin/sh
# install.sh - copy the skills (and optionally the commit gate) into place
#
# usage:
#   ./install.sh --home                 for yourself  -> ~/.claude/skills
#   ./install.sh /path/to/repo          for a project -> <repo>/.claude/skills
#                                       -> commit .claude/skills to share it
#   ./install.sh /path/to/repo --hooks  also the commit gate (.githooks, tools/)
#   ./install.sh /path/to/repo --hooks-only   the gate, and not the skills
#   ...            --claude-hooks       also the Claude Code hooks that ask for
#                                       coding-rules and the review note
#   ...            --claude-hooks-only  those hooks, and nothing else
#   ...            --force              replace what differs (how you update)
#
# Run without arguments, or with --help, to see this text.
#
# --claude-hooks goes with either target. For --home the commands point at
# ~/.claude/hooks and apply everywhere; for a project they point at
# ${CLAUDE_PROJECT_DIR} and can be committed, so the team gets them. Do not
# install both: hook settings merge across levels, so each hook would fire
# twice. The entries are merged into settings.json, never written over it.
#
# --claude-hooks-only exists because the hooks are worth having in a project
# that wants nothing else from this package: --claude-hooks alone also
# installs the skills and CLAUDE.md. It was added while a project with its
# own CLAUDE.md could not get the hooks at all -- the difference stopped the
# run, and the --force it suggested replaced that CLAUDE.md. That is fixed
# (ADR-001); the option stays because "only the hooks" is a real request.
#
# --hooks-only is for the common case of skills installed once in ~/.claude
# and a gate wanted in this repository: hooks are per-repository, since
# core.hooksPath is repository configuration, while skills need not be.
#
# Nothing is written until every destination has been checked. Anything
# already identical to this package is left alone and is not a conflict, so
# re-running after nothing changed just says so. What differs would be
# overwritten, and the run stops with a list and changes nothing -- an
# edited rule set or a modified hook is never lost to a re-run.
#
# --force means one thing: replace this package's own files with their newer
# versions. It is how you update. It never touches a file that holds your
# judgement, because those are not compared in the first place:
#
#   the team's rules/*.md          CLAUDE.md
#   tools/gate.conf               cq-baseline.txt
#   test-vocabulary.txt           private-allow.txt / refs-allow.txt
#   settings.json (merged only)   other people's hooks in .claude/hooks
#
# Do not give --force a second meaning. Wanting one is the sign that the
# ownership table below has a file in the wrong class -- fix the table.
# Measured what the second meaning costs (2026-08-28): CLAUDE.md was
# compared against the template, reported as an old version, and --force
# replaced a project's 123-line conventions with the 28-line template while
# printing "installed CLAUDE.md". See docs/install/design.md and
# docs/install/adr-001-file-ownership.md before changing any of this.
set -e
cd "$(dirname "$0")"

usage() {
  sed -n '2,/^set -e/p' "$0" | sed -e '/^set -e/d' -e 's/^# \{0,1\}//'
}

root=""
hooks=0
hooks_only=0
claude_hooks=0
claude_hooks_only=0
skills=1
force=0
home_install=0
[ "$#" -eq 0 ] && { usage; exit 0; }
for arg in "$@"; do
  case "$arg" in
    --home) home_install=1 ;;
    --hooks) hooks=1 ;;
    --hooks-only) hooks=1; hooks_only=1 ;;
    --claude-hooks) claude_hooks=1 ;;
    --claude-hooks-only) claude_hooks=1; claude_hooks_only=1 ;;
    --force) force=1 ;;
    -h|--help) usage; exit 0 ;;
    -*) echo "error: unknown option: $arg (try --help)" >&2; exit 2 ;;
    *)
      if [ -n "$root" ]; then
        echo "error: more than one project directory given" >&2
        exit 2
      fi
      root="$arg" ;;
  esac
done
if [ "$hooks_only" -eq 1 ] || [ "$claude_hooks_only" -eq 1 ]; then
  skills=0
fi

if [ "$home_install" -eq 1 ] && [ -n "$root" ]; then
  echo "error: --home and a project directory are two different targets" >&2
  exit 2
fi
if [ "$home_install" -eq 0 ] && [ -z "$root" ]; then
  echo "error: say where to install: --home, or a project directory (try --help)" >&2
  exit 2
fi

# source dir: skills/ in the distribution package, or .claude/skills when
# running from a repo that tracks the installed form
src=skills
[ -d "$src" ] || src=.claude/skills
if [ ! -d "$src" ] && [ "$skills" -eq 1 ]; then
  echo "error: no skills directory found next to install.sh" >&2
  exit 1
fi

if [ -n "$root" ]; then
  if [ ! -d "$root" ]; then
    echo "error: project directory not found: $root" >&2
    exit 1
  fi
  dest="$root/.claude/skills"
  claude_dest="$root/.claude/hooks"
  settings="$root/.claude/settings.json"
else
  dest="$HOME/.claude/skills"
  claude_dest="$HOME/.claude/hooks"
  settings="$HOME/.claude/settings.json"
fi

if [ "$claude_hooks" -eq 1 ] && [ ! -d claude-hooks ]; then
  echo "error: no claude-hooks directory found next to install.sh" >&2
  exit 1
fi

if [ "$hooks" -eq 1 ]; then
  if [ -z "$root" ]; then
    echo "error: --hooks needs a project directory (hooks live in a repo)" >&2
    exit 2
  fi
  if ! git -C "$root" rev-parse --git-dir >/dev/null 2>&1; then
    echo "error: not a git repository: $root" >&2
    exit 1
  fi
fi

# Installing into the repository that holds the sources: skills, CLAUDE.md and
# tools/ are already there and are the original, so copying them onto
# themselves would only destroy them. .githooks/ is still worth placing, since
# that is a different directory from the githooks/ they come from.
if [ "$skills" -eq 1 ]; then
  mkdir -p "$dest"
fi
self=0
if [ -n "$root" ] && [ "$(cd "$root" && pwd -P)" = "$(pwd -P)" ]; then
  self=1
fi

# ---- check every destination before writing anything --------------------
# Only what this script actually writes is checked, and only when the
# destination differs from what would be written: identical means a re-run,
# not a conflict. The old check flagged every tools/* file, including
# gate.conf and cq-baseline.txt, which are never written over at all.
gate_tools="check-metrics.py check-private.py check-refs.py check-trace.py \
check-text.py cq-baseline.template.txt test-vocabulary.template.txt \
private-allow.template.txt refs-allow.template.txt gate.conf.template \
textlint/textlintrc.template.yml textlint/textlintrc.en.template.yml \
textlint/allow.template.yml textlint/dict.template.js"

conflicts=""
add_conflict() {
  conflicts="${conflicts}  $1
"
}

# ---- who owns what -----------------------------------------------------
# Three classes, declared here because both the check above and the write
# below must read the same table (docs/install/design.md D-01, D-02):
#
#   package  ours: compared, and replaced on --force
#   user     the team's: never compared, never replaced
#   once     created when missing, never touched again -- not even by --force
#
# CLAUDE.md and the declaration files are "once" and so appear in neither the
# comparison nor any replacement. What is left to decide per file is the
# inside of a skill, which mixes the two: the active rule set is the team's,
# its *.template.md original is ours.
#
# Measured what happens when the two sides disagree (2026-08-28): a project's
# own CLAUDE.md was listed as an old version and --force replaced 123 lines of
# project conventions with the 28-line template, reporting success.
user_owned() {
  case "$1" in
    rules/*.template.md) return 1 ;;
    rules/*.md) return 0 ;;
    *) return 1 ;;
  esac
}

# Both halves report one path per line, relative to the skill, and both skip
# what the team owns. Per file rather than per directory: one difference --
# a rule file the installer itself had deleted -- took a diff -rq to find
# when the report named only the directory (D-04).
#
# Our files whose copy in the destination is missing or differs.
skill_diffs() {
  ( cd "$1" && find . -type f ) | sed 's|^\./||' | while read -r rel; do
    case "$rel" in *.pyc|*__pycache__*) continue ;; esac
    user_owned "$rel" && continue
    cmp -s "$1/$rel" "$2/$rel" 2>/dev/null || echo "$rel"
  done
}

# Files in the destination that this package does not have. An update
# replaces the whole skill directory, so these are what it would remove.
skill_extras() {
  ( cd "$2" && find . -type f ) | sed 's|^\./||' | while read -r rel; do
    case "$rel" in *.pyc|*__pycache__*) continue ;; esac
    user_owned "$rel" && continue
    [ -e "$1/$rel" ] || echo "$rel"
  done
}

skill_unchanged() {
  [ -z "$(skill_diffs "$1" "$2")$(skill_extras "$1" "$2")" ]
}

# ~/.claude/hooks holds other people's hooks too, so only our three files are
# ours to compare; an unrelated hook beside them is not a difference (D-01).
claude_hooks_unchanged() {
  for f in claude-hooks/*.py; do
    cmp -s "$f" "$claude_dest/$(basename "$f")" || return 1
  done
  return 0
}

if [ "$self" -eq 0 ] && [ "$skills" -eq 1 ]; then
  for d in "$src"/*/; do
    name=$(basename "$d")
    [ -e "$dest/$name" ] || continue
    for rel in $(skill_diffs "${d%/}" "$dest/$name"); do
      add_conflict "$dest/$name/$rel"
    done
    for rel in $(skill_extras "${d%/}" "$dest/$name"); do
      add_conflict "$dest/$name/$rel  (not from this package; an update removes it)"
    done
  done
fi
if [ "$hooks" -eq 1 ]; then
  for f in githooks/*; do
    t="$root/.githooks/$(basename "$f")"
    if [ -e "$t" ] && ! cmp -s "$f" "$t"; then
      add_conflict "$t"
    fi
  done
  if [ "$self" -eq 0 ]; then
    for n in $gate_tools; do
      if [ -e "$root/tools/$n" ] && ! cmp -s "tools/$n" "$root/tools/$n"; then
        add_conflict "$root/tools/$n"
      fi
    done
  fi
fi

if [ "$claude_hooks" -eq 1 ] && [ "$self" -eq 0 ]; then
  for f in claude-hooks/*.py; do
    t="$claude_dest/$(basename "$f")"
    if [ -e "$t" ] && ! cmp -s "$f" "$t"; then
      add_conflict "$t"
    fi
  done
fi

if [ -n "$conflicts" ] && [ "$force" -eq 0 ]; then
  echo "error: these differ from this package's versions and would be replaced:" >&2
  printf '%s' "$conflicts" >&2
  echo "nothing was installed." >&2
  echo "Unmarked lines are this package's own files, so they are older" >&2
  echo "versions from a previous install: re-run with --force to update them." >&2
  echo "The files that hold your judgement are not in this list and are never" >&2
  echo "replaced -- the team's rules, CLAUDE.md, gate.conf and the declaration" >&2
  echo "files are not compared at all." >&2
  echo "If you edited or added one of the files above, move it into this" >&2
  echo "repository first; --force replaces or removes it." >&2
  exit 1
fi

# ---- write ---------------------------------------------------------------
if [ "$self" -eq 1 ] && [ "$skills" -eq 1 ]; then
  echo "  skills already here (installing into their own repository)"
fi
uptodate=0
for d in "$src"/*/; do
  [ "$self" -eq 1 ] && break
  [ "$skills" -eq 0 ] && break
  name=$(basename "$d")
  if [ -e "$dest/$name" ] && skill_unchanged "${d%/}" "$dest/$name"; then
    uptodate=$((uptodate + 1))
    continue
  fi
  saved=""
  if [ -e "$dest/$name" ]; then
    # keep team-managed rule files (rules/*.md); only *.template.md is refreshed
    if [ -d "$dest/$name/rules" ]; then
      saved=$(mktemp -d)
      find "$dest/$name/rules" -maxdepth 1 -name '*.md' \
        ! -name '*.template.md' -exec cp {} "$saved"/ \;
    fi
    rm -rf "$dest/$name"
  fi
  cp -r "$d" "$dest/$name"
  if [ -n "$saved" ]; then
    # update install: restore the team's rule set exactly as it was
    mkdir -p "$dest/$name/rules"
    find "$dest/$name/rules" -maxdepth 1 -name '*.md' \
      ! -name '*.template.md' -delete 2>/dev/null || true
    cp "$saved"/* "$dest/$name/rules"/ 2>/dev/null || true
    rm -rf "$saved"
  else
    # fresh install: activate default rules from templates
    for t in "$dest/$name"/rules/*.template.md; do
      [ -f "$t" ] || continue
      m="${t%.template.md}.md"
      [ -e "$m" ] || cp "$t" "$m"
    done
  fi
  echo "  installed $name"
done
if [ "$uptodate" -gt 0 ]; then
  echo "  up to date: $uptodate skill(s) already match this package"
fi

# project install only: provide CLAUDE.md (project conventions) from the
# template, and only when the project has none. Home installs never touch
# ~/CLAUDE.md. An existing one is the project's own document -- 123 lines
# against the template's 28, in the one measured -- so it is never replaced,
# not even by --force (docs/install/design.md D-01, ADR-001).
if [ -n "$root" ] && [ -f CLAUDE.template.md ] && [ "$self" -eq 0 ] \
   && [ "$skills" -eq 1 ]; then
  if [ -e "$root/CLAUDE.md" ]; then
    echo "  kept CLAUDE.md (yours; merge from CLAUDE.template.md here if you"
    echo "    want the newer conventions)"
  else
    cp CLAUDE.template.md "$root/CLAUDE.md"
    echo "  installed CLAUDE.md (project conventions)"
  fi
fi

if [ "$claude_hooks" -eq 1 ]; then
  # Installing into the repository the hooks come from: name the originals
  # rather than keeping a second copy of them in step (as with core.hooksPath).
  register_args="--home"
  if [ -n "$root" ]; then
    register_args="--project"
    [ "$self" -eq 1 ] && register_args="--project --hooks-dir claude-hooks"
  fi
  if [ "$self" -eq 1 ]; then
    echo "  claude hooks already here (installing into their own repository)"
  elif claude_hooks_unchanged; then
    echo "  up to date: the Claude Code hooks already match this package"
  else
    mkdir -p "$claude_dest"
    cp claude-hooks/hooklib.py claude-hooks/coding-rules-reminder.py \
       claude-hooks/quality-note-check.py "$claude_dest/"
    chmod +x "$claude_dest/coding-rules-reminder.py" \
             "$claude_dest/quality-note-check.py"
    echo "  installed the Claude Code hooks to $claude_dest"
  fi
  # The settings file is the user's, so it is merged and never replaced. If
  # the merge cannot read it, the scripts stay where they are and it is said
  # plainly: half an install that claims success is worse than none.
  if ! python3 tools/register-claude-hooks.py $register_args \
       --settings "$settings"; then
    echo "the hook scripts are in place, but settings.json was left alone." >&2
    echo "fix the file named above, or add the entries by hand:" >&2
    echo "  python3 tools/register-claude-hooks.py $register_args \\" >&2
    echo "    --settings $settings --dry-run" >&2
    exit 1
  fi
fi

if [ "$hooks" -eq 1 ]; then
  mkdir -p "$root/tools"
  # Installing into the repository the hooks come from: point git at them
  # where they already are, rather than keeping a second copy in step.
  if [ "$self" -eq 1 ]; then
    hookdir=githooks
  else
    hookdir=.githooks
    mkdir -p "$root/.githooks"
    cp githooks/pre-commit githooks/pre-push githooks/commit-msg \
       "$root/.githooks/"
    chmod +x "$root/.githooks/pre-commit" "$root/.githooks/pre-push" \
             "$root/.githooks/commit-msg"
    mkdir -p "$root/tools/textlint"
    for n in $gate_tools; do
      # Some entries carry a subdirectory (textlint/), so copy to the same
      # relative place rather than flattening everything into tools/.
      cp "tools/$n" "$root/tools/$n"
    done
    chmod +x "$root/tools/check-metrics.py" "$root/tools/check-private.py" \
             "$root/tools/check-refs.py" "$root/tools/check-trace.py" \
             "$root/tools/check-text.py"
  fi
  # The project's own files: created when missing and never replaced, not even
  # by --force. gate.conf holds what this project measures, cq-baseline.txt the
  # findings it has accepted; neither can be regenerated from here.
  if [ ! -e "$root/tools/gate.conf" ]; then
    cp tools/gate.conf.template "$root/tools/gate.conf"
    echo "  created tools/gate.conf (what the gate measures here)"
  fi
  if [ ! -e "$root/tools/cq-baseline.txt" ]; then
    cp tools/cq-baseline.template.txt "$root/tools/cq-baseline.txt"
    echo "  created tools/cq-baseline.txt (empty declaration file)"
  fi
  git -C "$root" config core.hooksPath "$hookdir"
  echo "  hooks enabled from $hookdir/ (core.hooksPath set)"
  echo
  echo "next, in $root:"
  echo "  1. set ext= and scope= in tools/gate.conf"
  echo "  2. python3 tools/check-metrics.py --list   # what is flagged today"
  echo "     Nothing listed: you are done, the gate starts clean."
  echo "     Something listed: write the reason for each in"
  echo "     tools/cq-baseline.txt by hand -- do NOT pipe --list into it. If a"
  echo "     reason cannot be written, the code wants fixing first, and the"
  echo "     gate is better added after that (see README chapter 9)."
  echo "  3. to enable the private-data vocabulary check, copy"
  echo "     tools/test-vocabulary.template.txt to tools/test-vocabulary.txt"
  echo "     (without it, only the structural checks run)"
  echo "  4. optional, and only where Node is: to lint prose, copy"
  echo "     tools/textlint/textlintrc.template.yml to textlintrc.yml, install"
  echo "     what it names, and set text_scope in gate.conf. This check skips"
  echo "     itself where textlint is missing, so keep it to writing quality."
fi

if [ "$hooks_only" -eq 1 ]; then
  echo "done. the gate is installed; the skills were left alone."
  echo "check-metrics.py looks for cq-metrics.py in this repository first and"
  echo "then in ~/.claude/skills, so a home install of the skills is enough."
elif [ "$claude_hooks_only" -eq 1 ]; then
  echo "done. the Claude Code hooks are installed; nothing else was touched."
  echo "the hooks name the coding-rules skill, which they do not install:"
  echo "without it the reminder still fires and asks for rules that are not"
  echo "there, so install the skills too (--home, or a project install)."
else
  echo "done. installed to: $dest"
  echo "restart Claude Code (in the project directory, if project install) to pick up the skills."
  echo "try: python3 $dest/cq-review/cq-metrics.py <your-source-dir>"
fi
if [ "$claude_hooks" -eq 1 ]; then
  echo "the Claude Code hooks start at the next session (they are read at startup)."
fi
