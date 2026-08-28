#!/usr/bin/env python3
"""Put the three coding-discipline hooks into a Claude Code settings file.

This file is a copy. The original, and the install.sh that placed and
updates it, live in https://github.com/jam7/ai-dev-gates

The hooks themselves are in claude-hooks/; copying them somewhere does
nothing until settings.json names them, and that file also holds hooks
nobody here wrote. So this merges: it adds only what is missing, in its own
matcher group, and never rewrites a group it did not create.

An entry is recognised as ours by the script name and its arguments, not by
the path, so a copy that was installed for the home and is now being
installed for a project is updated rather than duplicated -- the two would
otherwise both fire and ask for the review note twice.

Usage:
  register-claude-hooks.py --home [--settings PATH] [--dry-run]
  register-claude-hooks.py --project --settings <repo>/.claude/settings.json
  register-claude-hooks.py --project --hooks-dir claude-hooks --settings ...

--hooks-dir is for the one case where the hooks are not copied: installing
into the repository they come from, where pointing at the originals keeps a
second copy from drifting out of step (install.sh does the same with
core.hooksPath).

--dry-run prints the resulting file instead of writing it. Otherwise the
previous file is kept as <settings>.bak before anything is written.

Exit codes: 0 done (including nothing to do), 2 the settings file could not
be read as the object this expects -- it is never overwritten in that case.
"""
import argparse
import json
import os
import sys

# Where the commands point. The home form stays unquoted so the shell
# expands ~; the project form quotes the variable, which Claude Code sets to
# the project root and which may hold spaces.
HOME_LOCATION = '~/.claude/hooks'
PROJECT_LOCATION = '"${CLAUDE_PROJECT_DIR}"/%s'
PROJECT_DEFAULT_DIR = '.claude/hooks'

# event, matcher (None where the event takes none), script, arguments
ENTRIES = (
    ('PreToolUse', 'Edit|Write', 'coding-rules-reminder.py', []),
    ('PostToolUse', 'Edit|Write', 'quality-note-check.py', ['--touched']),
    ('Stop', None, 'quality-note-check.py', ['--check']),
)

INDENT = 2


def command_for(script, args, location):
    return ' '.join(['python3', '%s/%s' % (location, script)] + args)


def is_ours(command, script, args):
    """Our hook wherever it was installed from: same script, same arguments."""
    tokens = command.replace('"', '').split()
    for index, token in enumerate(tokens):
        if token.endswith(script):
            return tokens[index + 1:] == args
    return False


def find_ours(groups, script, args):
    """The hook entry this run owns, or None if the event has none yet."""
    for group in groups:
        for hook in group.get('hooks', []):
            if hook.get('type') != 'command':
                continue
            if is_ours(hook.get('command', ''), script, args):
                return hook
    return None


def new_group(matcher, command):
    """A group of our own, so that removing it leaves other hooks alone."""
    group = {} if matcher is None else {'matcher': matcher}
    group['hooks'] = [{'type': 'command', 'command': command}]
    return group


def register(settings, location):
    """Add or update the three entries.

    Returns the report, one line per entry, and whether anything moved --
    a run that changes nothing must not rewrite the file, since that would
    replace the backup of the version worth keeping.
    """
    hooks = settings.setdefault('hooks', {})
    report, changed = [], False
    for event, matcher, script, args in ENTRIES:
        groups = hooks.setdefault(event, [])
        wanted = command_for(script, args, location)
        existing = find_ours(groups, script, args)
        if existing is None:
            groups.append(new_group(matcher, wanted))
            report.append('  registered %s (%s)' % (script, event))
            changed = True
        elif existing['command'] == wanted:
            report.append('  already registered %s (%s)' % (script, event))
        else:
            existing['command'] = wanted
            report.append('  updated %s to this install (%s)'
                          % (script, event))
            changed = True
    return report, changed


def load(path):
    """The settings as they are, {} when there is no file yet.

    Anything this cannot navigate raises: a settings file that is not the
    shape expected here is someone's configuration, and guessing at it would
    write over hooks that work.
    """
    if not os.path.exists(path):
        return {}
    with open(path, encoding='utf-8') as f:
        settings = json.load(f)
    if not isinstance(settings, dict):
        raise ValueError('the top level is not a JSON object')
    hooks = settings.get('hooks', {})
    if not isinstance(hooks, dict):
        raise ValueError('"hooks" is not a JSON object')
    for event, groups in hooks.items():
        if not isinstance(groups, list):
            raise ValueError('"hooks.%s" is not a JSON array' % event)
    return settings


def save(path, settings):
    """Write the merged file, keeping the previous one.

    True when there was a previous one to keep.
    """
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    backed_up = os.path.exists(path)
    if backed_up:
        with open(path, encoding='utf-8') as f:
            previous = f.read()
        with open(path + '.bak', 'w', encoding='utf-8') as f:
            f.write(previous)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(settings, f, indent=INDENT, ensure_ascii=False)
        f.write('\n')
    return backed_up


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument('--home', action='store_true',
                        help='commands point at ~/.claude/hooks')
    target.add_argument('--project', action='store_true',
                        help='commands point at ${CLAUDE_PROJECT_DIR}')
    parser.add_argument('--settings',
                        help='the settings file to merge into')
    parser.add_argument('--hooks-dir', default=PROJECT_DEFAULT_DIR,
                        help='with --project: where the hooks are, relative '
                             'to the project root (default %s)'
                             % PROJECT_DEFAULT_DIR)
    parser.add_argument('--dry-run', action='store_true',
                        help='print the result instead of writing it')
    return parser.parse_args()


def main():
    args = parse_args()
    location = (HOME_LOCATION if args.home
                else PROJECT_LOCATION % args.hooks_dir.strip('/'))
    default = ('~/.claude/settings.json' if args.home
               else os.path.join('.claude', 'settings.json'))
    path = os.path.expanduser(args.settings or default)

    try:
        settings = load(path)
    except (ValueError, OSError) as err:
        print('error: cannot read %s: %s' % (path, err), file=sys.stderr)
        print('nothing was written.', file=sys.stderr)
        return 2

    report, changed = register(settings, location)
    if args.dry_run:
        json.dump(settings, sys.stdout, indent=INDENT, ensure_ascii=False)
        sys.stdout.write('\n')
    elif not changed:
        report.append('  %s already names them; left alone' % path)
    elif save(path, settings):
        report.append('  merged into %s (previous kept as %s.bak)'
                      % (path, os.path.basename(path)))
    else:
        report.append('  created %s' % path)
    print('\n'.join(report))
    return 0


if __name__ == '__main__':
    sys.exit(main())
