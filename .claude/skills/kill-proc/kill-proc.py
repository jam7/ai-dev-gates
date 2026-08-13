#!/usr/bin/env python3
"""Kill only the processes whose command line matches a regex -- after
showing them.

Written because ad-hoc `ps | grep X | kill` and `pkill -f` procedures kept
killing bystanders: the grep itself, unrelated resident processes whose
command line happened to contain the word, and (the worst case) the calling
session's own ancestors. This tool reads /proc directly, so no grep appears
in its own results, and it always excludes itself, its ancestors, other
users' processes and kernel threads.

Two steps, on purpose:

  kill-proc.py 'REGEX'                list the matches; nothing is signalled
  kill-proc.py 'REGEX' --kill         send SIGTERM to exactly those
  kill-proc.py 'REGEX' --kill --signal KILL    only after TERM failed

The regex is searched against the full command line (procps `ps -ef` style,
arguments joined with spaces). Linux only (/proc).

Exit codes: 0 = matched (and signalled, with --kill), 1 = no match,
2 = usage error.
"""
import argparse
import os
import re
import signal
import sys


def ancestors():
    """This process and everything above it: killing the shell or the agent
    session that ran the tool is the accident this exists to prevent."""
    protected = set()
    pid = os.getpid()
    while pid > 0:
        protected.add(pid)
        try:
            with open('/proc/%d/status' % pid, encoding='ascii',
                      errors='replace') as f:
                text = f.read()
        except OSError:
            break
        m = re.search(r'^PPid:\s*(\d+)', text, re.M)
        if not m:
            break
        pid = int(m.group(1))
    return protected


def command_line(pid):
    """The full command line, or None for kernel threads and gone processes."""
    try:
        with open('/proc/%d/cmdline' % pid, 'rb') as f:
            raw = f.read()
    except OSError:
        return None
    if not raw:
        return None
    return raw.replace(b'\0', b' ').decode('utf-8', 'replace').strip()


def matches(pattern, include_other_users):
    """(pid, command) for every process the regex matches, bystanders
    excluded."""
    protected = ancestors()
    own_uid = os.getuid()
    found = []
    for entry in sorted(os.listdir('/proc')):
        if not entry.isdigit():
            continue
        pid = int(entry)
        if pid in protected:
            continue
        if not include_other_users:
            try:
                if os.stat('/proc/%d' % pid).st_uid != own_uid:
                    continue
            except OSError:
                continue
        cmd = command_line(pid)
        if cmd and pattern.search(cmd):
            found.append((pid, cmd))
    return found


def send(found, signame):
    signo = getattr(signal, 'SIG' + signame)
    status = 0
    for pid, cmd in found:
        try:
            os.kill(pid, signo)
            print('sent SIG%s to %d: %s' % (signame, pid, cmd[:100]))
        except ProcessLookupError:
            print('already gone: %d' % pid)
        except PermissionError:
            print('not permitted: %d: %s' % (pid, cmd[:100]), file=sys.stderr)
            status = 1
    return status


def parse_args():
    ap = argparse.ArgumentParser(
        description='Kill only the processes matching a regex, after '
                    'listing them.')
    ap.add_argument('regex', help='searched against the full command line')
    ap.add_argument('--kill', action='store_true',
                    help='send the signal; without this, only list')
    ap.add_argument('--signal', default='TERM', metavar='NAME',
                    choices=['TERM', 'INT', 'HUP', 'KILL'],
                    help='with --kill (default TERM; KILL only after '
                         'TERM failed)')
    ap.add_argument('--all-users', action='store_true',
                    help='do not restrict matches to your own processes')
    args = ap.parse_args()
    if not args.regex.strip():
        ap.error('an empty regex would match every process')
    try:
        args.pattern = re.compile(args.regex)
    except re.error as e:
        ap.error('bad regex: %s' % e)
    return args


def main():
    args = parse_args()
    found = matches(args.pattern, args.all_users)
    if not found:
        print('no process matches %r (self and ancestors are never listed)'
              % args.regex)
        return 1
    if not args.kill:
        for pid, cmd in found:
            print('%7d  %s' % (pid, cmd[:160]))
        print('\n%d match(es). Nothing was signalled -- check the list, '
              'then re-run with --kill.' % len(found))
        return 0
    return send(found, args.signal)


if __name__ == '__main__':
    sys.exit(main())
