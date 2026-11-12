#!/usr/bin/env python3
"""Run the integration's tests: python3 tests/run.py

The tests run the integration's own code against small stand-ins for the Home Assistant
modules it imports (tests/stubs) and a fake player, so they need nothing but Python 3.11+.
They check the integration's logic, not Home Assistant itself.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
STUBS, COMPONENTS = HERE / "stubs", HERE.parent / "custom_components"


def main() -> int:
    failed = 0
    with tempfile.TemporaryDirectory() as tmp:
        runs = [
            ["test_integration.py"],
            ["test_power.py"],
            ["test_mirror.py", str(HERE / "data" / "screen.h264"), str(Path(tmp) / "messages.json")],
        ]
        for name, *extra in runs:
            proc = subprocess.run(
                [sys.executable, str(HERE / name), str(STUBS), str(COMPONENTS), *extra],
                capture_output=True, text=True,
            )
            lines = proc.stdout.splitlines()
            bad = [line for line in lines if line.startswith("FAIL ")]
            ok = proc.returncode == 0 and not bad and any(line == "FAILED: 0" for line in lines)
            print(f"{'ok  ' if ok else 'FAIL'} {name}: {sum(line.startswith('PASS') for line in lines)} checks passed")
            if not ok:
                failed += 1
                print("\n".join(bad) or proc.stdout[-2000:])
                print(proc.stderr[-3000:])
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
