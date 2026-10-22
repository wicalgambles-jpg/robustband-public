# SPDX-License-Identifier: MIT
"""Portable entry: double click starts the browser app; arguments expose the CLI."""
import sys
from robustband.cli import main

if __name__=='__main__':
    sys.exit(main(sys.argv[1:] or ['ui']))
