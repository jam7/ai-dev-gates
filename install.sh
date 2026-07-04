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
  if [ -e "$dest/$name" ]; then
    printf '%s already exists in %s. overwrite? [y/N] ' "$name" "$dest"
    read -r ans
    if [ "$ans" != "y" ] && [ "$ans" != "Y" ]; then
      echo "  skipped $name"
      continue
    fi
    rm -rf "$dest/$name"
  fi
  cp -r "$d" "$dest/$name"
  echo "  installed $name"
done
echo "done. installed to: $dest"
echo "restart Claude Code (in the project directory, if project install) to pick up the skills."
echo "try: python3 $dest/cq-review/cq-metrics.py <your-source-dir>"
