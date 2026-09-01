#!/usr/bin/env python3
"""Run the deterministic, secret-free checks required before a final demo."""

from __future__ import annotations

import subprocess
import sys


CHECKS = (
    ("FASTLAB doctor", [sys.executable, "fastlab.py", "doctor"]),
    ("Dataset validation", [sys.executable, "fastlab.py", "validate"]),
    ("Offline regression suite", [sys.executable, "-m", "pytest", "-q"]),
)


def main() -> int:
    print("SPATHODEA final-readiness gate")
    for label, command in CHECKS:
        print(f"\n[RUN] {label}")
        result = subprocess.run(command, check=False)
        if result.returncode:
            print(f"\n[FAIL] {label} (exit {result.returncode})")
            return result.returncode
        print(f"[PASS] {label}")
    print("\nREADY: all deterministic offline checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

