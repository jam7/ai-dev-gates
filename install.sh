#!/bin/sh
# install.sh - copy skills into ~/.claude/skills or a project's .claude/skills
#
# usage:
#   ./install.sh                  install for yourself (~/.claude/skills)
#   ./install.sh /path/to/repo    install into a project (<repo>/.claude/skills)
#                                 -> commit .claude/skills to share with the team
set -e
cd "$(dirname "$0")"
# source dir: skills/ in the distribution package, or .claude/skills when
# running from a repo that tracks the installed form
src=skills
[ -d "$src" ] || src=.claude/skills
if [ ! -d "$src" ]; then
  echo "error: no skills directory found next to install.sh" >&2
  exit 1
fi
root=""
if [ $# -ge 1 ]; then
  root="$1"
  if [ ! -d "$root" ]; then
    echo "error: project directory not found: $root" >&2
    exit 1
  fi
  dest="$root/.claude/skills"
else
  dest="$HOME/.claude/skills"
fi
mkdir -p "$dest"
for d in "$src"/*/; do
  name=$(basename "$d")
  saved=""
  if [ -e "$dest/$name" ]; then
    printf '%s already exists in %s. overwrite? [y/N] ' "$name" "$dest"
    read -r ans
    if [ "$ans" != "y" ] && [ "$ans" != "Y" ]; then
      echo "  skipped $name"
      continue
    fi
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
  if [ -e "$root/CLAUDE.md" ]; then
    printf 'CLAUDE.md already exists in %s. overwrite with template? [y/N] ' "$root"
    read -r ans
    if [ "$ans" = "y" ] || [ "$ans" = "Y" ]; then
      cp CLAUDE.template.md "$root/CLAUDE.md"
      echo "  installed CLAUDE.md (project conventions)"
    else
      echo "  kept existing CLAUDE.md (merge conventions from CLAUDE.template.md if needed)"
    fi
  else
    cp CLAUDE.template.md "$root/CLAUDE.md"
    echo "  installed CLAUDE.md (project conventions)"
  fi
fi
echo "done. installed to: $dest"
echo "restart Claude Code (in the project directory, if project install) to pick up the skills."
echo "try: python3 $dest/cq-review/cq-metrics.py <your-source-dir>"
