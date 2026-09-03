"""Deterministic, non-production Harbor Freight Phase 0B-PREP checks."""
from __future__ import annotations
import argparse, hashlib, json, shutil, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

STATUSES = {"PASS", "FAIL", "SKIPPED", "NEEDS_DUSTIN"}
REQUIRED_CATEGORY_IDS = {"git_repositories","canonical_state","configuration","receipts_and_execution_history","authorization_and_identity","docker_persistent_state","windows_recovery_dependencies","large_archival_data","off_device_backup_targets"}
REQUIRED_FIELDS = {"id","restore_priority","state_type","sensitivity","backup_required","rebuildable","discovery","verification_method","restore_method","interactive_dustin_required","currently_verified","notes"}
FIXTURE_FILES = {"identity.txt": b"JOSIE-HARBOR-FREIGHT-PHASE0B\n", "state/config.json": b'{"fixture":true,"schema":1}\n'}
HEX = set("0123456789abcdef")

def validate_sha256(value: str) -> None:
    if not isinstance(value, str) or len(value) != 64 or any(c not in HEX for c in value):
        raise ValueError("SHA-256 must be exactly 64 lowercase hexadecimal characters")

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""): digest.update(chunk)
    value = digest.hexdigest(); validate_sha256(value); return value

def validate_manifest(path: Path) -> dict[str, Any]:
    try: data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc: raise ValueError(f"manifest cannot be loaded: {exc}") from exc
    if data.get("schema_version") != 1: raise ValueError("manifest schema_version must equal 1")
    sets = data.get("recovery_sets")
    if not isinstance(sets, dict) or set(sets) != {"CORE_JOSIE_RECOVERY","FULL_DATA_RECOVERY"}: raise ValueError("both recovery sets are required")
    categories = data.get("categories")
    if not isinstance(categories, list) or len(categories) < 9: raise ValueError("at least 9 categories are required")
    seen = set()
    for item in categories:
        if not isinstance(item, dict): raise ValueError("every category must be an object")
        missing = REQUIRED_FIELDS - set(item)
        if missing: raise ValueError(f"category {item.get('id')!r} missing {sorted(missing)}")
        cid = item["id"]
        if not isinstance(cid, str) or not cid or cid in seen: raise ValueError(f"invalid or duplicate id {cid!r}")
        seen.add(cid)
        if item["restore_priority"] not in sets: raise ValueError(f"invalid priority for {cid}")
        discovery = item["discovery"]
        if not isinstance(discovery, dict) or not discovery.get("method") or not discovery.get("paths"): raise ValueError(f"missing discovery/path information for {cid}")
        for field in ("backup_required","rebuildable","interactive_dustin_required","currently_verified"):
            if not isinstance(item[field], bool): raise ValueError(f"{cid}.{field} must be boolean")
    if REQUIRED_CATEGORY_IDS - seen: raise ValueError(f"missing categories {sorted(REQUIRED_CATEGORY_IDS-seen)}")
    for name, details in sets.items():
        members = details.get("categories") if isinstance(details, dict) else None
        if not isinstance(members, list) or not members or not set(members) <= seen: raise ValueError(f"invalid recovery set {name}")
    return data

def manifest_category_count(path: Path) -> int: return len(validate_manifest(path)["categories"])

def _beneath(path: Path, parent: Path) -> bool:
    try: path.relative_to(parent); return True
    except ValueError: return False

def validate_fixture_target(target: Path, allowed_root: Path) -> tuple[Path, Path]:
    target, allowed_root = target.resolve(), allowed_root.resolve()
    dangerous = {Path(target.anchor).resolve(), Path("C:/Josie").resolve()}
    if target in dangerous or allowed_root in dangerous or target == allowed_root: raise ValueError("dangerous production or filesystem-root target refused")
    if not _beneath(target, allowed_root): raise ValueError("target must be beneath explicit temporary root")
    if allowed_root.exists() and not allowed_root.is_dir(): raise ValueError("temporary root is not a directory")
    if target.exists(): raise ValueError("fixture target must not already exist")
    return target, allowed_root

def _result(cid: str, status: str, evidence: dict[str, Any]) -> dict[str, Any]:
    if status not in STATUSES: raise ValueError(f"invalid status {status}")
    return {"id":cid,"status":status,"evidence":evidence}

def run_fixture(target: Path, allowed_root: Path) -> dict[str, Any]:
    target, allowed_root = validate_fixture_target(target, allowed_root); created = False
    source, backup, restored = (target/name for name in ("source","backup","restored"))
    try:
        allowed_root.mkdir(parents=True, exist_ok=True); target.mkdir(); created = True
        for relative, content in FIXTURE_FILES.items():
            destination = source/relative; destination.parent.mkdir(parents=True, exist_ok=True); destination.write_bytes(content)
        expected = {name:{"sha256":sha256_file(source/name),"bytes":(source/name).stat().st_size} for name in FIXTURE_FILES}
        shutil.copytree(source, backup); shutil.rmtree(source); shutil.copytree(backup, restored)
        actual = {name:{"sha256":sha256_file(restored/name),"bytes":(restored/name).stat().st_size} for name in FIXTURE_FILES}
        status = "PASS" if actual == expected else "FAIL"
        return {"schema_version":1,"mode":"VerifyFixture","status":status,"production_changed":False,"external_write":False,"results":[_result("fixture_round_trip",status,{"files":actual,"source_deleted_before_restore":True})]}
    finally:
        if created and target.exists(): shutil.rmtree(target)

def dry_run(manifest: Path) -> dict[str, Any]:
    return {"schema_version":1,"mode":"DryRun","status":"PASS","production_changed":False,"external_write":False,"results":[_result("manifest","PASS",{"category_count":manifest_category_count(manifest)}),_result("fixture_round_trip","SKIPPED",{"reason":"DryRun never writes"}),_result("attended_facts","NEEDS_DUSTIN",{"reason":"physical/off-device facts are not machine-provable"})]}

def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n",encoding="utf-8")

def git_commit(repo: Path) -> str:
    value = subprocess.run(["git","rev-parse","HEAD"],cwd=repo,text=True,capture_output=True,check=True).stdout.strip()
    if len(value) != 40 or any(c not in HEX for c in value): raise ValueError("invalid full git commit SHA")
    return value

def generate_evidence(repo: Path, output: Path, intentional_files: Iterable[str], focused: dict[str,int], full_suite: dict[str,Any], timestamp: str|None=None) -> dict[str,Any]:
    normalized = sorted(set(intentional_files)); files=[]
    for relative in normalized:
        path=repo/relative; files.append({"path":relative,"sha256":sha256_file(path),"bytes":path.stat().st_size})
    for key in ("count","exit_code"):
        if not isinstance(focused.get(key),int) or focused[key] < 0: raise ValueError(f"invalid focused test {key}")
    payload={"schema_version":1,"evidence_scope":"parent_commit_and_phase0b_content","git_commit_sha":git_commit(repo),"changed_files":normalized+[output.relative_to(repo).as_posix()],"files":files,"self_reference":"Evidence excludes its own digest; embedding it would be self-referential. git_commit_sha is the parent at generation time.","manifest_category_count":manifest_category_count(repo/"config/harbor-freight-backup-manifest.json"),"focused_tests":focused,"full_suite":full_suite,"timestamp":timestamp or datetime.now(timezone.utc).isoformat(),"push_performed":False}
    write_json(output,payload); return payload

def main(argv: list[str]|None=None) -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("--mode",choices=("DryRun","VerifyFixture"),default="DryRun"); parser.add_argument("--manifest",type=Path,required=True); parser.add_argument("--target",type=Path); parser.add_argument("--allowed-root",type=Path); parser.add_argument("--allow-temporary-write",action="store_true"); parser.add_argument("--receipt",type=Path); args=parser.parse_args(argv)
    try:
        validate_manifest(args.manifest)
        if args.mode=="DryRun":
            if args.receipt: raise ValueError("DryRun refuses receipt writes")
            payload=dry_run(args.manifest)
        else:
            if not args.allow_temporary_write: raise PermissionError("VerifyFixture requires --allow-temporary-write")
            if args.target is None or args.allowed_root is None or args.receipt is None: raise ValueError("VerifyFixture requires target, allowed-root, and receipt")
            payload=run_fixture(args.target,args.allowed_root); write_json(args.receipt,payload)
        print(json.dumps(payload,sort_keys=True)); return 0 if payload["status"]=="PASS" else 1
    except (ValueError,PermissionError,OSError) as exc:
        print(json.dumps({"schema_version":1,"status":"FAIL","error":str(exc)}),file=sys.stderr); return 2

if __name__=="__main__": sys.exit(main())
