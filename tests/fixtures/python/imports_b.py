# The same five imports as imports_a.py, and nothing else in common.
import json
import os
import re
import sys
from pathlib import Path


def narrow(text):
    return re.sub(r"\s+", " ", json.dumps(sys.path[:1]) + text)
