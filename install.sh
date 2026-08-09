#!/bin/sh
# install.sh - copy the skills (and optionally the commit gate) into place
#
# usage:
#   ./install.sh                        for yourself  -> ~/.claude/skills
#   ./install.sh /path/to/repo          for a project -> <repo>/.claude/skills
#                                       -> commit .claude/skills to share it
#   ./install.sh /path/to/repo --hooks  also the commit gate (.githooks, tools/)
#   ...            --force              replace what is already installed
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
force=0
for arg in "$@"; do
  case "$arg" in
    --hooks) hooks=1 ;;
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
if [ ! -d "$src" ]; then
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

# ---- check every destination before writing anything --------------------
conflicts=""
add_conflict() {
  conflicts="${conflicts}  $1
"
}

for d in "$src"/*/; do
  if [ -e "$dest/$(basename "$d")" ]; then
    add_conflict "$dest/$(basename "$d")"
  fi
done
if [ -n "$root" ] && [ -f CLAUDE.template.md ] && [ -e "$root/CLAUDE.md" ]; then
  add_conflict "$root/CLAUDE.md"
fi
if [ "$hooks" -eq 1 ]; then
  for f in githooks/* tools/*; do
    case "$f" in githooks/*) sub=.githooks ;; *) sub=tools ;; esac
    if [ -e "$root/$sub/$(basename "$f")" ]; then
      add_conflict "$root/$sub/$(basename "$f")"
    fi
  done
fi

if [ -n "$conflicts" ] && [ "$force" -eq 0 ]; then
  echo "error: these already exist and would be replaced:" >&2
  printf '%s' "$conflicts" >&2
  echo "nothing was installed. re-run with --force to replace them." >&2
  exit 1
fi

# ---- write ---------------------------------------------------------------
mkdir -p "$dest"
for d in "$src"/*/; do
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
if [ -n "$root" ] && [ -f CLAUDE.template.md ]; then
  cp CLAUDE.template.md "$root/CLAUDE.md"
  echo "  installed CLAUDE.md (project conventions)"
fi

if [ "$hooks" -eq 1 ]; then
  mkdir -p "$root/.githooks" "$root/tools"
  cp githooks/pre-commit githooks/pre-push "$root/.githooks/"
  chmod +x "$root/.githooks/pre-commit" "$root/.githooks/pre-push"
  cp tools/check-metrics.py tools/check-private.py "$root/tools/"
  cp tools/cq-baseline.template.txt tools/test-vocabulary.template.txt \
     "$root/tools/"
  chmod +x "$root/tools/check-metrics.py" "$root/tools/check-private.py"
  # Declaration files hold the project's own judgements, so they are created
  # when missing and never replaced -- not even by --force.
  if [ ! -e "$root/tools/cq-baseline.txt" ]; then
    cp tools/cq-baseline.template.txt "$root/tools/cq-baseline.txt"
    echo "  created tools/cq-baseline.txt (empty declaration file)"
  fi
  git -C "$root" config core.hooksPath .githooks
  echo "  installed .githooks/ and tools/ (core.hooksPath set)"
  echo
  echo "next, in $root:"
  echo "  1. set ext= and scope= at the top of .githooks/pre-commit"
  echo "  2. python3 tools/check-metrics.py --list   # the findings you have now"
  echo "     declare the ones worth keeping in tools/cq-baseline.txt, with the"
  echo "     reason; fix the rest. Until then the gate fails every commit"
  echo "  3. to enable the private-data vocabulary check, copy"
  echo "     tools/test-vocabulary.template.txt to tools/test-vocabulary.txt"
  echo "     (without it, only the structural checks run)"
fi

echo "done. installed to: $dest"
echo "restart Claude Code (in the project directory, if project install) to pick up the skills."
echo "try: python3 $dest/cq-review/cq-metrics.py <your-source-dir>"
