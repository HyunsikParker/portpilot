"""The build host: a Windows machine with QNX SDP 8.0, QEMU, CMake, Ninja, Git and Python 3.

PortPilot either runs on that machine (LocalHost) or drives it from another computer through a worker command that
offers `windows <powershell>`, `push <local> <path>` and `pull <path> <local>` (WorkerHost); the reference setup drives
a Windows laptop from a Mac this way.

Settings come from the environment, or from a .portpilot.env file (KEY=VALUE lines) in the current directory:
  PORTPILOT_SDP          QNX SDP 8.0 directory, the one holding qnxsdp-env.bat       (default C:\\qnx800)
  PORTPILOT_WORK         work directory for upstream copies and build trees           (default %USERPROFILE%\\portpilot)
  PORTPILOT_VM           directory for the mkqnximage VM images                       (default <work>\\vm)
  PORTPILOT_HOST_PYTHON  Python 3 on the build host                                   (default python)
  PORTPILOT_QEMU         QEMU install directory                                       (default C:\\Program Files\\qemu)
  PORTPILOT_HOST_CC      host C compiler for code generators that read HOSTCC         (default gcc)
  PORTPILOT_WORKER       worker command for a remote build host (unset: run locally)
  PORTPILOT_WORKER_ROOT  directory on the build host that the worker's paths are relative to
"""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path, PureWindowsPath


def _settings():
    env = {}
    f = Path(".portpilot.env")
    if f.exists():
        for line in f.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = os.path.expanduser(v.strip())
    env.update({k: v for k, v in os.environ.items() if k.startswith("PORTPILOT_")})
    return env


class Host:
    def __init__(self, env):
        self.sdp = env.get("PORTPILOT_SDP", r"C:\qnx800")
        self.work = env.get("PORTPILOT_WORK", str(PureWindowsPath(os.environ.get("USERPROFILE", r"C:\Users\Public"),
                                                                    "portpilot")))
        self.vm = env.get("PORTPILOT_VM", self.work + r"\vm")
        self.python = env.get("PORTPILOT_HOST_PYTHON", "python")
        self.qemu = env.get("PORTPILOT_QEMU", r"C:\Program Files\qemu")
        self.cc = env.get("PORTPILOT_HOST_CC", "gcc")
        self.sdp_env = self.sdp + r"\qnxsdp-env.bat"

    def ps(self, script, timeout=7200):
        """Run a PowerShell script on the build host; returns stdout and stderr together."""
        raise NotImplementedError

    def put(self, local, remote):
        raise NotImplementedError

    def get(self, remote, local):
        raise NotImplementedError

    def run_bat(self, text, remote, timeout=7200):
        """Copy a batch file to the build host and run it; returns its output."""
        local = Path(tempfile.mkdtemp(prefix="portpilot-")) / PureWindowsPath(remote).name
        local.write_text(text.replace("\r\n", "\n").replace("\n", "\r\n"), newline="")
        self.put(local, remote)
        return self.ps(f"cmd /c '{remote}'", timeout=timeout)


class LocalHost(Host):
    def ps(self, script, timeout=7200):
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                           capture_output=True, text=True, timeout=timeout)
        return r.stdout + r.stderr

    def put(self, local, remote):
        Path(remote).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(local, remote)

    def get(self, remote, local):
        if Path(remote).exists():
            shutil.copyfile(remote, local)


class WorkerHost(Host):
    def __init__(self, env):
        super().__init__(env)
        self.worker = os.path.expanduser(env["PORTPILOT_WORKER"])
        self.root = env.get("PORTPILOT_WORKER_ROOT", self.work).rstrip("\\")

    def _rel(self, remote):
        if not remote.lower().startswith(self.root.lower() + "\\"):
            raise ValueError(f"{remote} is outside the worker root {self.root}")
        return remote[len(self.root) + 1:].replace("\\", "/")

    def _call(self, *args, timeout=7200):
        r = subprocess.run([self.worker, *args], capture_output=True, text=True, timeout=timeout)
        return r.stdout + r.stderr

    def ps(self, script, timeout=7200):
        return self._call("windows", script, timeout=timeout)

    def put(self, local, remote):
        parent = str(PureWindowsPath(remote).parent)
        self.ps(f"New-Item -ItemType Directory -Force '{parent}' | Out-Null")
        self._call("push", str(local), self._rel(remote))

    def get(self, remote, local):
        self._call("pull", self._rel(remote), str(local))


def from_env():
    env = _settings()
    return WorkerHost(env) if env.get("PORTPILOT_WORKER") else LocalHost(env)
