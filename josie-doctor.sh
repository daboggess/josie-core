#!/usr/bin/env bash
# Windows/Git Bash entry point. No installation or repairs.
set -u
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*)
    if [[ ! -f "$script_dir/.venv/Scripts/python.exe" ]]; then
      printf '%s\n' 'FAIL | Existing Josie Windows Python is missing. No installation attempted.'
      exit 1
    fi
    exec "$script_dir/.venv/Scripts/python.exe" -B "$script_dir/scripts/josie_doctor.py" "$@"
    ;;
  *)
    printf '%s\n' 'WARN | Josie runs on Windows. Use Git Bash, not the WindowsApps/WSL bash shim.'
    printf '%s\n' 'WARN | Or run: C:\Josie\.venv\Scripts\python.exe -B C:\Josie\scripts\josie_doctor.py'
    exit 0
    ;;
esac
