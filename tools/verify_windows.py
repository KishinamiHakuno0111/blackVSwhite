"""Run the actual distribution EXE alone, with Python paths removed."""

import json
import os
from pathlib import Path
import shutil
import subprocess


def main():
    project = Path(__file__).resolve().parents[1]
    isolated = project / "artifacts" / "standalone" / "中文路径 空格"
    isolated.mkdir(parents=True, exist_ok=True)
    executable = isolated / "BlackWhiteChess.exe"
    shutil.copy2(project / "dist" / executable.name, executable)
    report = isolated / "smoke-report.json"
    if report.exists():
        report.unlink()
    env = os.environ.copy()
    for name in tuple(env):
        if name.upper().startswith(("PYTHON", "_PYI")) or name.upper() in ("TCL_LIBRARY", "TK_LIBRARY"):
            env.pop(name)
    windows = Path(os.environ["SystemRoot"])
    env["PATH"] = os.pathsep.join((str(windows / "System32"), str(windows)))
    completed = subprocess.run([str(executable), "--smoke-test", str(report)],
                               cwd=isolated, env=env, timeout=90, check=False)
    if not report.exists():
        raise RuntimeError(f"No verification report; exit code {completed.returncode}")
    result = json.loads(report.read_text(encoding="utf-8"))
    result["isolated_directory"] = str(isolated)
    result["test_path"] = env["PATH"]
    result["exit_code"] = completed.returncode
    output = project / "artifacts" / "packaging-verification.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if completed.returncode != 0 or not result["ok"] or not result["frozen"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
