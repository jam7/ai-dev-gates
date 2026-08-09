# Five line-level imports, shared verbatim with imports_b.py. Two modules
# needing the same five name them the same way, and no language lets that list
# be shared -- so this must not be reported as duplication.
import json
import os
import re
import sys
from pathlib import Path


def widen(value):
    return Path(os.fspath(value)).resolve()
