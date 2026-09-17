"""Read-only Windows Josie diagnostics. No inference, secrets, restarts or repairs."""
from __future__ import annotations
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener

ROOT = Path(__file__).resolve().parents[1]
STORAGE = Path("I:/Josie-Storage")
OLLAMA = STORAGE / "apps/Ollama/0.32.5/ollama.exe"
EXPECTED_MODEL = "josie-local:1.0"
LOCAL_URLS = frozenset(f"http://127.0.0.1:{port}{path}" for port, path in [
    (11434, "/api/version"), (11434, "/api/tags"), (11434, "/api/ps"),
    (3000, "/health"), (8790, "/health"), (5678, "/healthz"),
    (3010, "/health"), (8788, "/health")])
# Fixed native read-only query; no commands are taken from config or CLI input.
WINDOWS_QUERY = r"""
$ErrorActionPreference='Stop'
$o=[ordered]@{}
try {$o.os=Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version,BuildNumber,@{Name='LastBootUpTime';Expression={$_.LastBootUpTime.ToString('o')}},@{Name='UptimeHours';Expression={[math]::Round(([datetime]::Now-$_.LastBootUpTime).TotalHours,2)}},TotalVisibleMemorySize,FreePhysicalMemory} catch {$o.os=$null}
try {$o.cpu=Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors,LoadPercentage} catch {$o.cpu=$null}
try {$o.disks=@(Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' | Select-Object DeviceID,Size,FreeSpace)} catch {$o.disks=@()}
try {$o.gpu=@(Get-CimInstance Win32_VideoController | Select-Object Name,DriverVersion,Status)} catch {$o.gpu=$null}
try {$o.pagefile=@(Get-CimInstance Win32_PageFileUsage | Select-Object Name,AllocatedBaseSize,CurrentUsage)} catch {$o.pagefile=@()}
try {$o.ports=@(Get-NetTCPConnection -State Listen | Select-Object LocalAddress,LocalPort,OwningProcess)} catch {$o.ports=@()}
try {$o.ip=@(Get-NetIPAddress -AddressFamily IPv4 | Where-Object AddressState -eq Preferred | Select-Object InterfaceAlias,IPAddress)} catch {$o.ip=@()}
try {$o.tasks=@(Get-ScheduledTask -TaskPath '\Josie\' | ForEach-Object {[pscustomobject]@{Name=$_.TaskName;State=[string]$_.State;Enabled=$_.Settings.Enabled}})} catch {$o.tasks=@()}
try {$o.firewall=@(Get-NetFirewallRule | Where-Object {$_.DisplayName -match 'Ollama' -and $_.Enabled -eq 'True' -and $_.Direction -eq 'Inbound' -and $_.Action -eq 'Allow'} | ForEach-Object {$r=$_;[pscustomobject]@{Name=$r.DisplayName;Profile=[string]$r.Profile;Program=($r | Get-NetFirewallApplicationFilter).Program;Remote=@(($r | Get-NetFirewallAddressFilter).RemoteAddress)}})} catch {$o.firewall=$null}
try {$p=Join-Path $env:APPDATA 'Docker\settings-store.json';$d=Get-Content -LiteralPath $p -Raw | ConvertFrom-Json;$o.dockerAutoStart=$d.AutoStart} catch {$o.dockerAutoStart=$null}
$o | ConvertTo-Json -Depth 5 -Compress
"""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Diagnostic redirects are forbidden")


def run_read(command, timeout=15):
    """Fixed diagnostic commands only. Discard raw stderr, including on failure."""
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, check=False, shell=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return result.returncode == 0, result.stdout if result.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return False, ""


def get_json(url):
    if url not in LOCAL_URLS:
        raise ValueError("Not an approved local diagnostic URL")
    with build_opener(ProxyHandler({}), NoRedirect()).open(url, timeout=5) as response:
        data = response.read(2_000_001)
        if len(data) > 2_000_000:
            raise ValueError("Diagnostic response too large")
        return json.loads(data)


def sqlite_health(path):
    if not path.is_file():
        return False, "missing; no database created"
    try:
        connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=3)
        try:
            result = connection.execute("PRAGMA quick_check").fetchone()[0]
        finally:
            connection.close()
        return result == "ok", "quick_check=" + str(result == "ok")
    except sqlite3.Error:
        return False, "read-only integrity check unavailable"


class Report:
    def __init__(self):
        self.rows = []

    def add(self, status, section, detail):
        self.rows.append({"status": status, "check": section, "detail": str(detail)})

    def finish(self, as_json=False):
        counts = dict(Counter(row["status"] for row in self.rows))
        if as_json:
            print(json.dumps({"checks": self.rows, "summary": counts, "read_only": True}, indent=2))
        else:
            print("JOSIE DOCTOR - read-only Windows diagnostics")
            for row in self.rows:
                print(f"{row['status']:4} | {row['check']}: {row['detail']}")
            print("SUMMARY | " + " ".join(f"{k}={counts.get(k, 0)}" for k in ("PASS", "WARN", "FAIL")))
            print("No repairs, restarts, inference, installation, or configuration writes performed.")
        return int(counts.get("FAIL", 0) > 0)


def check_models(report, tags, resident):
    names = [item.get("name", "") for item in tags.get("models", [])]
    report.add("PASS" if EXPECTED_MODEL in names else "FAIL", "Ollama expected model", EXPECTED_MODEL)
    for item in tags.get("models", []):
        report.add("PASS", "Installed model", f"{item.get('name')} | {item.get('size')} bytes")
    loaded = resident.get("models", [])
    if not loaded:
        report.add("PASS", "Ollama residency", "No model loaded; normal after keep-alive expiry")
        report.add("WARN", "Ollama GPU use", "Not measurable while no model is loaded")
    for model in loaded:
        report.add("PASS", "Ollama residency",
                   f"{model.get('name')} | context={model.get('context_length')} | VRAM bytes={model.get('size_vram')}")
        report.add("PASS" if model.get("size_vram", 0) else "WARN", "Ollama GPU use",
                   "GPU memory allocated" if model.get("size_vram", 0) else "CPU residency; expected pre-GPU")


def check_gpu(report, gpus, smi):
    if gpus is None:
        report.add("WARN", "GPU OS query", "Unavailable; do not infer absence")
    elif not any("nvidia" in item.get("Name", "").lower() for item in gpus):
        report.add("WARN", "NVIDIA GPU", "Not present yet in Windows display inventory")
    else:
        for item in gpus:
            if "nvidia" in item.get("Name", "").lower():
                report.add("PASS", "NVIDIA GPU", f"{item['Name']} | driver={item.get('DriverVersion')}")
    if not smi:
        report.add("WARN", "nvidia-smi", "Not installed/found; expected pre-GPU. No installation attempted.")
        report.add("WARN", "NVIDIA driver / VRAM / CUDA", "Not available yet")
        return
    ok, output = run_read([str(smi), "--query-gpu=name,driver_version,memory.total,memory.used,memory.free,temperature.gpu",
                           "--format=csv,noheader,nounits"])
    report.add("PASS" if ok else "WARN", "nvidia-smi",
               "name, driver, total/used/free MiB, degrees C: " + output.strip()[:1000] if ok else "Present but query failed")
    ok, output = run_read([str(smi)])
    match = re.search(r"CUDA Version:\s*([0-9.]+)", output) if ok else None
    report.add("PASS" if match else "WARN", "CUDA driver capability",
               match.group(1) + " (driver capability, not proof of CUDA Toolkit)" if match else "Unavailable")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print the same safe results as JSON")
    args = parser.parse_args(argv)
    report = Report()
    if os.name != "nt":
        report.add("WARN", "Host", "Windows deployment: use existing Windows Python, not a Linux/WSL interpreter.")
        return report.finish(args.json)
    ps = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    ok, output = run_read([str(ps), "-NoProfile", "-NonInteractive", "-Command", WINDOWS_QUERY], timeout=25)
    try:
        native = json.loads(output) if ok else {}
    except ValueError:
        native = {}
    os_info = native.get("os")
    if os_info:
        report.add("PASS", "OS", f"{os_info['Caption']} {os_info['Version']} build {os_info['BuildNumber']}")
        report.add("PASS", "Uptime", f"{os_info['UptimeHours']} hours; last boot {os_info['LastBootUpTime']}")
        used = (os_info["TotalVisibleMemorySize"] - os_info["FreePhysicalMemory"]) / 1048576
        free = os_info["FreePhysicalMemory"] / 1048576
        report.add("PASS" if free > 2 else "WARN", "RAM", f"used={used:.2f} GiB free={free:.2f} GiB")
    else:
        report.add("WARN", "Windows metrics", "OS/CIM query unavailable; rerun in a normal host shell")
    report.add("PASS" if native.get("cpu") else "WARN", "CPU", json.dumps(native.get("cpu")))
    report.add("WARN", "Load average", "Linux 1/5/15-minute load is not a Windows metric; CPU LoadPercentage reported instead")
    report.add("PASS" if native.get("pagefile") else "WARN", "Pagefile MiB", json.dumps(native.get("pagefile")))
    for disk in native.get("disks", []):
        free = disk["FreeSpace"] / 2**30
        status = "FAIL" if free < 2 else "WARN" if free < 20 else "PASS"
        report.add(status, "Disk " + disk["DeviceID"],
                   f"free={free:.2f} GiB total={disk['Size']/2**30:.2f} GiB used={(disk['Size']-disk['FreeSpace'])/2**30:.2f} GiB")
    if not native.get("disks"):
        report.add("WARN", "Disks", "Unavailable")
    report.add("PASS" if native.get("ip") else "WARN", "IP information", json.dumps(native.get("ip", [])))
    ports = native.get("ports", [])
    for port in (3000, 11434, 8790, 5678, 3010, 8788, 443):
        listeners = [f"{r['LocalAddress']} pid={r['OwningProcess']}" for r in ports if r["LocalPort"] == port]
        report.add("PASS" if listeners else "WARN", f"Listener {port}", ", ".join(listeners) or "Not observed")
    broad = [r for r in (native.get("firewall") or []) if "Any" in r.get("Remote", [])
             and "ollama" in str(r.get("Program", "")).lower()]
    report.add("WARN" if broad or native.get("firewall") is None else "PASS", "Ollama firewall",
               f"{len(broad)} broad enabled application allow rule(s); Docker-only rule is not exclusive"
               if broad else "No broad rule seen" if native.get("firewall") is not None else "Unable to inspect")
    report.add("PASS" if native.get("dockerAutoStart") is True else "WARN", "Docker sign-in startup",
               "AutoStart=true" if native.get("dockerAutoStart") is True else "AutoStart false/unknown; manual Docker Desktop launch may be required")
    for task in native.get("tasks", []):
        report.add("PASS" if task["Enabled"] else "WARN", "Scheduled task", f"{task['Name']} | {task['State']} | enabled={task['Enabled']}")
    report.add("PASS", "systemd / cron", "Windows host; Josie uses Task Scheduler, not systemd or host cron")
    for relative in (".venv/Scripts/python.exe", ".env", "deploy/.env.services", "deploy/compose.yaml",
                     "config", "data", "scripts", "data/private/conversation-control.token"):
        path = ROOT / relative
        report.add("PASS" if path.exists() else "FAIL", "Required path", path)
    for path in (STORAGE, STORAGE / "models/ollama", OLLAMA):
        report.add("PASS" if path.exists() else "FAIL", "Required storage", path)
    for relative in ("config/opencode-local.json", "data/tools/gemini-cli/package.json",
                     "data/private/local-code-jobs", "data/private/codex-delegations"):
        path = ROOT / relative
        report.add("PASS" if path.exists() else "WARN", "Optional path", path)
    report.add("PASS", "Python", sys.version.split()[0] + " | " + sys.executable)
    for port, path, critical in [(11434, "/api/version", True), (3000, "/health", True),
                                  (8790, "/health", True), (5678, "/healthz", False),
                                  (3010, "/health", False), (8788, "/health", False)]:
        url = f"http://127.0.0.1:{port}{path}"
        try:
            value = get_json(url)
            success = bool(value.get("version")) if port == 11434 else value.get("status") in ("ok", True)
            report.add("PASS" if success else "FAIL" if critical else "WARN", "Local API",
                       url + (" responsive" if success else " unhealthy"))
            if port == 11434:
                report.add("PASS", "Ollama version", value.get("version", "unknown"))
            if port == 8790:
                for seat, data in value.get("cli_seats", {}).items():
                    if isinstance(data, dict) and "installed" in data:
                        report.add("PASS" if data["installed"] else "WARN", "Optional consultant " + seat,
                                   "installation detected; authentication/quota not exercised" if data["installed"] else "unavailable")
        except Exception:
            report.add("FAIL" if critical else "WARN", "Local API", url + " unavailable; no restart attempted")
    try:
        check_models(report, get_json("http://127.0.0.1:11434/api/tags"), get_json("http://127.0.0.1:11434/api/ps"))
    except Exception:
        report.add("WARN", "Ollama models", "Could not read model inventory")
    docker = shutil.which("docker.exe")
    if not docker:
        fallback = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/DockerDesktop/resources/bin/docker.exe"
        docker = str(fallback) if fallback.is_file() else None
    report.add("PASS" if docker else "FAIL", "Docker installation", docker or "not found")
    daemon = False
    if docker:
        daemon, version = run_read([docker, "version", "--format", "Client={{.Client.Version}} Server={{.Server.Version}}"])
        report.add("PASS" if daemon else "FAIL", "Docker daemon", version.strip() if daemon else "unavailable; not started")
    if daemon:
        ok, output = run_read([docker, "ps", "-a", "--format", "{{json .}}"])
        containers = [json.loads(line) for line in output.splitlines() if line] if ok else []
        for name in ("josie-open-webui-1", "josie-n8n-1", "josie-browser-worker-1", "josie-proposal-server-1"):
            row = next((r for r in containers if r.get("Names") == name), {})
            good = row.get("State") == "running" and "unhealthy" not in row.get("Status", "")
            report.add("PASS" if good else "FAIL" if name == "josie-open-webui-1" else "WARN",
                       "Container " + name, row.get("Status", "missing"))
        for row in containers:
            if row.get("State") != "running" or "unhealthy" in row.get("Status", ""):
                report.add("WARN", "Stopped/unhealthy container", row.get("Names"))
        for name in ("josie_open_webui_data", "josie_n8n_data"):
            ok, out = run_read([docker, "volume", "inspect", name, "--format", "{{.Name}} | {{.Mountpoint}}"])
            report.add("PASS" if ok else "FAIL", "Persistent volume", out.strip() if ok else name + " missing")
        ok, out = run_read([docker, "compose", "ls", "--format", "json"])
        if ok:
            projects = json.loads(out)
            report.add("PASS", "Compose projects", ", ".join(f"{p['Name']} {p['Status']}" for p in projects))
        else:
            report.add("WARN", "Compose projects", "unavailable")
        code = "import sqlite3; c=sqlite3.connect('file:/app/backend/data/webui.db?mode=ro',uri=True); print(c.execute('PRAGMA quick_check').fetchone()[0]); c.close()"
        ok, out = run_read([docker, "exec", "josie-open-webui-1", "python", "-B", "-c", code])
        report.add("PASS" if ok and out.strip() == "ok" else "FAIL", "Open WebUI data",
                   "read-only SQLite quick_check=" + str(ok and out.strip() == "ok"))
    ts = Path("C:/Program Files/Tailscale/tailscale.exe")
    if ts.is_file():
        ok, out = run_read([str(ts), "status", "--json"])
        try:
            state = json.loads(out) if ok else {}
            running = state.get("BackendState") == "Running" and state.get("Self", {}).get("Online") is True
            report.add("PASS" if running else "WARN", "Tailscale",
                       f"state={state.get('BackendState')} online={state.get('Self',{}).get('Online')} DNS={state.get('Self',{}).get('DNSName')}")
            report.add("WARN" if state.get("Health") else "PASS", "Tailscale health", f"{len(state.get('Health') or [])} warning(s)")
        except ValueError:
            report.add("WARN", "Tailscale", "status unavailable")
        ok, out = run_read([str(ts), "serve", "status"])
        report.add("PASS" if ok else "WARN", "Private reverse proxy", out.strip() if ok else "Serve status unavailable")
    else:
        report.add("WARN", "Tailscale", "not installed; desktop-local chat may still work")
    ok, detail = sqlite_health(ROOT / "data/josie.db")
    report.add("PASS" if ok else "FAIL", "Josie SQLite", detail)
    for directory in (ROOT / "data/backups", STORAGE / "backups/josie-database"):
        backups = list(directory.glob("josie-*.db")) if directory.is_dir() else []
        latest = max(backups, key=lambda p: p.stat().st_mtime) if backups else None
        if latest:
            ok, detail = sqlite_health(latest)
            age = (time.time() - latest.stat().st_mtime) / 3600
            report.add("FAIL" if not ok else "WARN" if age > 36 else "PASS", "SQLite backup",
                       f"{latest} | age={age:.1f}h | {detail}")
        else:
            report.add("WARN", "SQLite backup", str(directory) + " has no checkpoints")
    backups = list((STORAGE / "backups/services").glob("open-webui-*.tgz"))
    latest = max(backups, key=lambda p: p.stat().st_mtime) if backups else None
    report.add("WARN", "Full service recovery",
               str(latest) + " | compare archive age/contents with live image/filter; not restore-verified by doctor"
               if latest else "No full Open WebUI archive in existing service-backup directory")
    smi = shutil.which("nvidia-smi.exe")
    if not smi:
        for path in (Path("C:/Windows/System32/nvidia-smi.exe"),
                     Path("C:/Program Files/NVIDIA Corporation/NVSMI/nvidia-smi.exe")):
            if path.is_file():
                smi = str(path)
                break
    check_gpu(report, native.get("gpu"), smi)
    for path in (ROOT / "logs/ollama-background.log",
                 Path(os.environ.get("LOCALAPPDATA", "")) / "Ollama/server.log"):
        if path.is_file():
            with path.open("rb") as stream:
                stream.seek(max(0, path.stat().st_size - 131072))
                tail = stream.read(131072).decode("utf-8", errors="replace")
            matches = len(re.findall(r"(?im)^.*(?:cuda|nvidia|gpu).*(?:error|fail).*$|^.*(?:error|fail).*(?:cuda|nvidia|gpu).*$", tail))
            age = (time.time() - path.stat().st_mtime) / 3600
            report.add("WARN" if matches or age > 24 else "PASS", "GPU log scan",
                       f"{path} | tail matches={matches} | file age={age:.1f}h; raw text withheld")
    report.add("PASS", "Inference", "Not run by doctor; use separately opt-in measure_pre_gpu.py")
    return report.finish(args.json)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("FAIL | Diagnostic incomplete (" + type(exc).__name__ + "); no repair attempted.")
        raise SystemExit(1)
