# SPDX-License-Identifier: GPL-3.0-or-later
"""Small standalone launcher shipped only inside the optional Piper plugin.

The proprietary DARK process never imports Piper. It starts this worker as a
child process and speaks Wyoming over loopback. Keep this shim in the separate
plugin artifact and publish its source with that component.
"""
from __future__ import annotations

import asyncio
import sys


def main() -> int:
    if sys.platform == "win32":
        # Wyoming Piper registers signal handlers that asyncio does not support
        # on Windows. DARK owns this child process and shuts it down directly.
        def ignore_add_signal_handler(self, sig, callback, *args):
            return None

        def ignore_remove_signal_handler(self, sig):
            return False

        asyncio.BaseEventLoop.add_signal_handler = ignore_add_signal_handler
        asyncio.BaseEventLoop.remove_signal_handler = ignore_remove_signal_handler

    from wyoming_piper.__main__ import run

    run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
