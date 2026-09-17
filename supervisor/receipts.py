from __future__ import annotations

import json
import os
import uuid
from pathlib import Path


def write_receipt(directory: Path, receipt: dict, receipt_id: str | None = None) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    rid = receipt_id or str(uuid.uuid4())
    target = directory / f"{rid}.json"
    if target.exists():
        raise FileExistsError(f"receipt already exists: {target}")
    temporary = directory / f".{rid}.{uuid.uuid4().hex}.tmp"
    payload = dict(receipt, receipt_id=rid)
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        if target.exists():
            raise FileExistsError(f"receipt already exists: {target}")
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return target


def read_receipt(path: Path | str) -> dict:
    if isinstance(path, str):
        path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"receipt file does not exist: {path}")
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError:
        raise ValueError(f"receipt file is not valid JSON: {path}")
    if not isinstance(data, dict):
        raise ValueError(f"receipt file does not contain a dictionary: {path}")
    if not data.get("schema_version"):
        raise ValueError(f"receipt file is missing 'schema_version': {path}")
    if not data.get("receipt_id"):
        raise ValueError(f"receipt file is missing 'receipt_id': {path}")
    return data


def find_receipt(directory: Path | str, job_id: str) -> tuple[dict, Path] | None:
    if isinstance(directory, str):
        directory = Path(directory)
    if not directory.exists() or not directory.is_dir():
        return None
    receipts = []
    for file in directory.glob("*.json"):
        if not file.name.startswith("."):
            try:
                receipt = read_receipt(file)
                receipts.append((receipt, file))
            except (FileNotFoundError, ValueError):
                continue
    if not receipts:
        return None
    receipts.sort(key=lambda x: x[1].stat().st_mtime, reverse=True)
    for receipt, path in receipts:
        if receipt.get("job_id") == job_id:
            return (receipt, path)
    return None
