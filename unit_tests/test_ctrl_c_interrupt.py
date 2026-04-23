#!/usr/local/bin/local_python
from __future__ import annotations

import os
import shutil
from pathlib import Path

def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    local_python = "/usr/local/bin/local_python"
    runner_path = repo_root / "dev" / "dev_common" / "win_python_runner.py"
    target_module = "dev.dev_common.win_python_interrupt_target"
    if shutil.which("cmd.exe") is None:
        print("cmd.exe not found; Windows interop unavailable in this environment.")
        return 2
    cmd = [local_python, str(runner_path), "--module", target_module, "--package-root", str(repo_root)]
    print("Launching runner in foreground. Press Ctrl+C manually to test interrupt handling.")
    print("Command:", " ".join(cmd))
    os.chdir(str(repo_root))
    os.execv(cmd[0], cmd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
