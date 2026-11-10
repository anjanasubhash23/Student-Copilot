"""Run an LLM-written numerical solution and read the number it prints.

The code comes from a model that read user-uploaded text, so it is treated as hostile:
- a separate Python process (-I -S: no site packages, no environment, no user directories),
  with an empty environment, a throwaway working directory and a timeout;
- an audit hook installed before the code runs, which it cannot remove, refuses network access,
  starting processes, loading native code, and opening files other than the standard library's;
- CPU-time and file-size limits where the OS supports them.
Only the last line of stdout is used, and only if it parses as a number.
"""

import math
import subprocess
import sys
import tempfile
from dataclasses import dataclass

GUARD = r"""
import sys
try:
    import resource
    _cpu = int(sys.argv[1])
    resource.setrlimit(resource.RLIMIT_CPU, (_cpu, _cpu))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
except (ImportError, ValueError, OSError):
    pass
_ALLOWED = tuple(p for p in {sys.prefix, sys.base_prefix, sys.exec_prefix, sys.base_exec_prefix} if p)
_BLOCKED = ("socket.", "subprocess.", "os.system", "os.exec", "os.spawn", "os.posix_spawn", "os.fork",
            "os.kill", "os.remove", "os.rename", "os.rmdir", "os.mkdir", "os.unlink", "os.chmod", "os.putenv",
            "shutil.", "ctypes.", "urllib.", "http.", "ftplib.", "smtplib.", "webbrowser.", "pty.", "fcntl.",
            "mmap.", "winreg.", "sqlite3.", "compile_dll")
def _hook(event, args):
    if event.startswith(_BLOCKED):
        raise PermissionError(f"blocked: {event}")
    if event == "open":
        path, mode = args[0], (args[1] or "r")
        if isinstance(path, int) or any(c in str(mode) for c in "wax+"):
            raise PermissionError("blocked: open")
        if not str(path).startswith(_ALLOWED):
            raise PermissionError("blocked: open")
sys.addaudithook(_hook)
del _hook
_code = sys.stdin.read()
exec(compile(_code, "<solution>", "exec"), {"__name__": "__main__"})
"""


@dataclass
class RunResult:
    value: float | None
    error: str | None = None


def run_solution(code: str, timeout: float = 5.0) -> RunResult:
    cpu = max(1, math.ceil(timeout))
    with tempfile.TemporaryDirectory() as cwd:
        try:
            proc = subprocess.run(
                # Limits are set by the child itself: preexec_fn isn't safe in a multithreaded parent.
                [sys.executable, "-I", "-S", "-c", GUARD, str(cpu)],
                input=code,
                capture_output=True,
                text=True,
                timeout=timeout,
                env={},
                cwd=cwd,
            )
        except subprocess.TimeoutExpired:
            return RunResult(None, f"timed out after {timeout:g}s")
    if proc.returncode != 0:
        last = (proc.stderr.strip().splitlines() or ["error"])[-1]
        return RunResult(None, last[:300])
    lines = proc.stdout.strip().splitlines()
    if not lines:
        return RunResult(None, "printed nothing")
    try:
        value = float(lines[-1].strip())
    except ValueError:
        return RunResult(None, f"last line isn't a number: {lines[-1][:80]!r}")
    if not math.isfinite(value):
        return RunResult(None, "not a finite number")
    return RunResult(value)
