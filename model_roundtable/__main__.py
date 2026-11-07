"""Allow `python -m model_roundtable` to run the CLI.

Copyright (c) 2026 Asdale Dynamics, LLC
"""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
