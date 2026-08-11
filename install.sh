#!/bin/sh
# install.sh - copy the skills (and optionally the commit gate) into place
#
# usage:
#   ./install.sh                        for yourself  -> ~/.claude/skills
#   ./install.sh /path/to/repo          for a project -> <repo>/.claude/skills
#                                       -> commit .claude/skills to share it
#   ./install.sh /path/to/repo --hooks  also the commit gate (.githooks, tools/)
#   ./install.sh /path/to/repo --hooks-only   the gate, and not the skills
#   ...            --force              replace what is already installed
#
# --hooks-only is for the common case of skills installed once in ~/.claude
# and a gate wanted in this repository: hooks are per-repository, since
# core.hooksPath is repository configuration, while skills need not be.
#
# Nothing is written until every destination has been checked. If anything
# would be overwritten the run stops with a list and changes nothing, so an
# edited rule set or a modified hook is never lost to a re-run; --force is how
# you say to replace it. Even then, two kinds of file are kept: the team's
# rules/*.md, and the declaration files (tools/cq-baseline.txt,
# tools/test-vocabulary.txt), which hold judgements this package cannot
# regenerate.
set -e
cd "$(dirname "$0")"

root=""
hooks=0
hooks_only=0
force=0
for arg in "$@"; do
  case "$arg" in
    --hooks) hooks=1 ;;
    --hooks-only) hooks=1; hooks_only=1 ;;
    --force) force=1 ;;
    -*) echo "error: unknown option: $arg" >&2; exit 2 ;;
    *)
      if [ -n "$root" ]; then
        echo "error: more than one project directory given" >&2
        exit 2
      fi
      root="$arg" ;;
  esac
done

# source dir: skills/ in the distribution package, or .claude/skills when
# running from a repo that tracks the installed form
src=skills
[ -d "$src" ] || src=.claude/skills
if [ ! -d "$src" ] && [ "$hooks_only" -eq 0 ]; then
  echo "error: no skills directory found next to install.sh" >&2
  exit 1
fi

if [ -n "$root" ]; then
  if [ ! -d "$root" ]; then
    echo "error: project directory not found: $root" >&2
    exit 1
  fi
  dest="$root/.claude/skills"
else
  dest="$HOME/.claude/skills"
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
if [ "$hooks_only" -eq 0 ]; then
  mkdir -p "$dest"
fi
self=0
if [ -n "$root" ] && [ "$(cd "$root" && pwd -P)" = "$(pwd -P)" ]; then
  self=1
fi

# ---- check every destination before writing anything --------------------
conflicts=""
add_conflict() {
  conflicts="${conflicts}  $1
"
}

if [ "$self" -eq 0 ] && [ "$hooks_only" -eq 0 ]; then
  for d in "$src"/*/; do
    if [ -e "$dest/$(basename "$d")" ]; then
      add_conflict "$dest/$(basename "$d")"
    fi
  done
  if [ -n "$root" ] && [ -f CLAUDE.template.md ] && [ -e "$root/CLAUDE.md" ]; then
    add_conflict "$root/CLAUDE.md"
  fi
fi
if [ "$hooks" -eq 1 ]; then
  for f in githooks/*; do
    if [ -e "$root/.githooks/$(basename "$f")" ]; then
      add_conflict "$root/.githooks/$(basename "$f")"
    fi
  done
  if [ "$self" -eq 0 ]; then
    for f in tools/*; do
      if [ -e "$root/tools/$(basename "$f")" ]; then
        add_conflict "$root/tools/$(basename "$f")"
      fi
    done
  fi
fi

if [ -n "$conflicts" ] && [ "$force" -eq 0 ]; then
  echo "error: these already exist and would be replaced:" >&2
  printf '%s' "$conflicts" >&2
  echo "nothing was installed. re-run with --force to replace them." >&2
  exit 1
fi

# ---- write ---------------------------------------------------------------
if [ "$self" -eq 1 ] && [ "$hooks_only" -eq 0 ]; then
  echo "  skills already here (installing into their own repository)"
fi
for d in "$src"/*/; do
  [ "$self" -eq 1 ] && break
  [ "$hooks_only" -eq 1 ] && break
  name=$(basename "$d")
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

# project install only: provide CLAUDE.md (project conventions) from template.
# Home installs never touch ~/CLAUDE.md.
if [ -n "$root" ] && [ -f CLAUDE.template.md ] && [ "$self" -eq 0 ] \
   && [ "$hooks_only" -eq 0 ]; then
  cp CLAUDE.template.md "$root/CLAUDE.md"
  echo "  installed CLAUDE.md (project conventions)"
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
    cp tools/check-metrics.py tools/check-private.py "$root/tools/"
    cp tools/cq-baseline.template.txt tools/test-vocabulary.template.txt \
       tools/private-allow.template.txt tools/gate.conf.template "$root/tools/"
    chmod +x "$root/tools/check-metrics.py" "$root/tools/check-private.py"
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
fi

if [ "$hooks_only" -eq 1 ]; then
  echo "done. the gate is installed; the skills were left alone."
  echo "check-metrics.py looks for cq-metrics.py in this repository first and"
  echo "then in ~/.claude/skills, so a home install of the skills is enough."
else
  echo "done. installed to: $dest"
  echo "restart Claude Code (in the project directory, if project install) to pick up the skills."
  echo "try: python3 $dest/cq-review/cq-metrics.py <your-source-dir>"
fi
