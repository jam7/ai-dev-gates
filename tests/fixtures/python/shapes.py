"""Shapes the indentation scanner has to get right.

The docstring itself matters: an apostrophe in it, like don't, and a `#` must
not be read as code. Blanking the content is what makes the lines below it
line up.
"""
import os
import re
from collections import (
    OrderedDict,
    defaultdict,
)

CONST = re.compile(r"['\"]#")


# An apostrophe in a comment: this is the one that swallowed a whole file,
# because Python's comments aren't C's directives.
def flat(a, b):
    total = a + b
    return total


class Holder:
    """A class, so methods report as Holder.method and self is not a param."""

    def __init__(self, root, mode):
        self.root = root
        self.mode = mode

    def deep(self, items):
        for item in items:
            if item:
                for part in item:
                    if part:
                        while part:
                            part -= 1
        return items

    @staticmethod
    def chain(value):
        # An elif chain is one level, the way `} else if (...) {` is.
        if value == 1:
            return "one"
        elif value == 2:
            return "two"
        elif value == 3:
            return "three"
        elif value == 4:
            return "four"
        return "many"


def wrapped(
        first,
        second,
        third):
    """A signature split across lines still has three parameters."""
    joined = os.path.join(
        first,
        second,
        third)
    return joined


def continued(value):
    # A backslash continuation is layout, not nesting.
    result = value and \
        value > 0 and \
        value < 100
    return result


def outer(seed):
    """A nested def is reported on its own, and counts inside its parent."""

    def inner(extra):
        return seed + extra

    return inner(1)
