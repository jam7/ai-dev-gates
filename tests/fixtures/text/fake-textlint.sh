#!/bin/sh
# A stand-in for textlint, so the wrapper's wiring can be fixed without Node
# on the machine running the tests: what it passes (config, then the files in
# scope), and that it relays the output and the exit status untouched.
echo "fake-textlint invoked"
echo "  args: $*"
cat <<'REPORT'

tests/fixtures/text/sample.md
  3:5  error  canned finding  fake-rule

REPORT
exit 1
