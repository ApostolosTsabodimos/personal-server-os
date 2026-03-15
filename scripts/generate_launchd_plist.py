#!/usr/bin/env python3
"""
PSO launchd plist generator — macOS only.

Generates a launchd user agent plist that starts the PSO dashboard
automatically on login and restarts it if it crashes.

Usage (called automatically by `pso install-daemon` on macOS):
    python3 scripts/generate_launchd_plist.py \
        --python  /path/to/python3 \
        --pso-dir /path/to/personal-server-os \
        --log     ~/.pso_dev/dashboard.log \
        --output  ~/Library/LaunchAgents/com.pso.dashboard.plist

Can also be run standalone to preview the generated plist:
    python3 scripts/generate_launchd_plist.py --dry-run
"""

import argparse
import os
import sys
import shutil
from pathlib import Path


LABEL = "com.pso.dashboard"


def find_python(pso_dir: Path) -> str:
    """Find best Python — venv first, then system."""
    for candidate in [
        pso_dir / ".venv" / "bin" / "python3",
        pso_dir / "venv"  / "bin" / "python3",
    ]:
        if candidate.exists():
            return str(candidate)
    system = shutil.which("python3")
    if system:
        return system
    raise RuntimeError("python3 not found — install Python 3 or create a venv first")


def generate_plist(python: str, pso_dir: Path, log: Path) -> str:
    """
    Return the plist XML as a string.

    Key launchd directives used:
      RunAtLoad           — start immediately when loaded (login)
      KeepAlive           — restart automatically if the process exits
      ThrottleInterval    — wait 10s before restarting to avoid tight loops
      StandardOutPath /
      StandardErrorPath   — both go to the same log file
      EnvironmentVariables — PYTHONUNBUFFERED so Flask output isn't buffered
    """
    web_dir  = pso_dir / "web"
    api_path = web_dir / "api.py"

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>

    <!-- Service identity -->
    <key>Label</key>
    <string>{LABEL}</string>

    <!-- Command to run -->
    <key>ProgramArguments</key>
    <array>
        <string>{python}</string>
        <string>{api_path}</string>
    </array>

    <!-- Working directory (api.py expects to be run from web/) -->
    <key>WorkingDirectory</key>
    <string>{web_dir}</string>

    <!-- Start at login -->
    <key>RunAtLoad</key>
    <true/>

    <!-- Restart if it crashes -->
    <key>KeepAlive</key>
    <true/>

    <!-- Wait 10s before restarting to avoid tight crash loops -->
    <key>ThrottleInterval</key>
    <integer>10</integer>

    <!-- Log both stdout and stderr to the dashboard log -->
    <key>StandardOutPath</key>
    <string>{log}</string>
    <key>StandardErrorPath</key>
    <string>{log}</string>

    <!-- Ensure Flask output isn't buffered -->
    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTHONUNBUFFERED</key>
        <string>1</string>
    </dict>

</dict>
</plist>
"""


def main():
    parser = argparse.ArgumentParser(
        description="Generate a launchd plist for the PSO dashboard (macOS)"
    )
    parser.add_argument(
        "--python",
        default=None,
        help="Path to python3 executable (auto-detected if omitted)",
    )
    parser.add_argument(
        "--pso-dir",
        default=str(Path(__file__).parent.parent),
        help="Path to PSO root directory (default: parent of scripts/)",
    )
    parser.add_argument(
        "--log",
        default=str(Path.home() / ".pso_dev" / "dashboard.log"),
        help="Path to log file (default: ~/.pso_dev/dashboard.log)",
    )
    parser.add_argument(
        "--output",
        default=str(Path.home() / "Library" / "LaunchAgents" / "com.pso.dashboard.plist"),
        help="Where to write the plist (default: ~/Library/LaunchAgents/com.pso.dashboard.plist)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the generated plist to stdout without writing",
    )
    args = parser.parse_args()

    pso_dir = Path(args.pso_dir).expanduser().resolve()
    log     = Path(args.log).expanduser()
    output  = Path(args.output).expanduser()

    # Validate PSO dir
    if not (pso_dir / "web" / "api.py").exists():
        print(f"Error: api.py not found at {pso_dir}/web/api.py", file=sys.stderr)
        print("Make sure --pso-dir points to the PSO root directory.", file=sys.stderr)
        sys.exit(1)

    # Resolve Python
    try:
        python = args.python or find_python(pso_dir)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    plist = generate_plist(python=python, pso_dir=pso_dir, log=log)

    if args.dry_run:
        print(plist)
        return

    # Ensure log directory exists
    log.parent.mkdir(parents=True, exist_ok=True)

    # Write plist
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(plist)

    print(f"Plist written to: {output}")


if __name__ == "__main__":
    main()