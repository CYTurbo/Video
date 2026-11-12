"""Tiny progress logger: everything goes to logs/studio.log, important lines also to the console."""
from __future__ import annotations

import datetime as _dt

from . import config

_LOG = config.LOGS / "studio.log"


def log(msg: str, echo: bool = True) -> None:
    config.LOGS.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(_LOG, "a", encoding="utf-8") as f:
        for line in str(msg).splitlines() or [""]:
            f.write(f"[{stamp}] {line}\n")
    if echo:
        print(msg, flush=True)
