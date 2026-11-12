#!/usr/bin/env python3
"""Entry point: python studio.py <command> ...  (see `python studio.py -h`)."""
import sys

from studio.cli import main

if __name__ == "__main__":
    sys.exit(main())
