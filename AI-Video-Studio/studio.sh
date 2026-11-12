#!/usr/bin/env bash
# Linux/macOS launcher
HERE="$(cd "$(dirname "$0")" && pwd)"
exec "$HERE/.venv/bin/python" "$HERE/studio.py" "$@"
