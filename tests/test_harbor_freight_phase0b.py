import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path
from unittest import mock
from josie.harbor_freight_phase0b import (REQUIRED_CATEGORY_IDS, REQUIRED_FIELDS, generate_evidence, run_fixture, sha256_file, validate_fixture_target, validate_manifest, validate_sha256)

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "config/harbor-freight-backup-manifest.json"
MODULE = [sys.executable, "-m", "josie.harbor_freight_phase0b"]

class Phase0BTests(unittest.TestCase):
    def test_manifest_contains_required_nine_categories(self):
        data=validate_manifest(MANIFEST); ids={x["id"] for x in data["categories"]}
        self.assertGreaterEqual(len(ids),9); self.assertTrue(REQUIRED_CATEGORY_IDS <= ids)

    def test_every_category_contains_required_fields_and_discovery_paths(self):
        for item in validate_manifest(MANIFEST)["categories"]:
            self.assertTrue(REQUIRED_FIELDS <= set(item)); self.assertTrue(item["discovery"]["paths"])

    def test_malformed_manifest_fails_validation(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"bad.json"; path.write_text('{"schema_version":1,"categories":[]}',encoding="utf-8")
            with self.assertRaises(ValueError): validate_manifest(path)

    def test_default_dry_run_performs_no_writes(self):
        with tempfile.TemporaryDirectory() as td:
            before=set(Path(td).iterdir())
            environment=os.environ.copy(); environment["PYTHONPATH"]=str(ROOT)
            done=subprocess.run(MODULE+["--manifest",str(MANIFEST)],cwd=td,text=True,capture_output=True,env=environment)
            self.assertEqual(done.returncode,0,done.stderr); self.assertEqual(set(Path(td).iterdir()),before)
            payload=json.loads(done.stdout); self.assertEqual(payload["mode"],"DryRun"); self.assertFalse(payload["production_changed"])

    def test_verify_fixture_requires_explicit_write_authorization(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td)/"allowed"; target=base/"fixture"; receipt=base/"receipt.json"
            done=subprocess.run(MODULE+["--mode","VerifyFixture","--manifest",str(MANIFEST),"--allowed-root",str(base),"--target",str(target),"--receipt",str(receipt)],cwd=ROOT,text=True,capture_output=True)
            self.assertEqual(done.returncode,2); self.assertFalse(base.exists()); self.assertIn("requires --allow-temporary-write",done.stderr)

    def test_fixture_round_trip_is_byte_identical_sha256(self):
        with tempfile.TemporaryDirectory() as td:
            allowed=Path(td)/"allowed"; result=run_fixture(allowed/"run",allowed)
            self.assertEqual(result["status"],"PASS")
            for evidence in result["results"][0]["evidence"]["files"].values(): validate_sha256(evidence["sha256"]); self.assertGreater(evidence["bytes"],0)

    def test_dangerous_and_non_temporary_targets_are_rejected(self):
        with self.assertRaises(ValueError): validate_fixture_target(Path("C:/Josie"),Path("C:/Josie"))
        with tempfile.TemporaryDirectory() as td:
            allowed=Path(td)/"allowed"
            with self.assertRaises(ValueError): validate_fixture_target(Path(td)/"outside",allowed)

    def test_nonempty_arbitrary_target_is_rejected_and_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            allowed=Path(td)/"allowed"; target=allowed/"run"; target.mkdir(parents=True); marker=target/"keep.txt"; marker.write_text("keep",encoding="utf-8")
            with self.assertRaises(ValueError): run_fixture(target,allowed)
            self.assertEqual(marker.read_text(encoding="utf-8"),"keep")

    def test_cleanup_removes_only_generated_fixture_paths(self):
        with tempfile.TemporaryDirectory() as td:
            allowed=Path(td)/"allowed"; allowed.mkdir(); sentinel=allowed/"sentinel.txt"; sentinel.write_text("untouched",encoding="utf-8")
            run_fixture(allowed/"generated",allowed)
            self.assertFalse((allowed/"generated").exists()); self.assertEqual(sentinel.read_text(encoding="utf-8"),"untouched")

    def test_json_receipt_has_status_and_evidence_fields(self):
        with tempfile.TemporaryDirectory() as td:
            allowed=Path(td)/"allowed"; receipt=allowed/"receipt.json"
            done=subprocess.run(MODULE+["--mode","VerifyFixture","--manifest",str(MANIFEST),"--allow-temporary-write","--allowed-root",str(allowed),"--target",str(allowed/"run"),"--receipt",str(receipt)],cwd=ROOT,text=True,capture_output=True)
            self.assertEqual(done.returncode,0,done.stderr); payload=json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"],"PASS"); self.assertIn("evidence",payload["results"][0]); self.assertFalse(payload["external_write"])

    def test_validation_failure_has_deterministic_nonzero_exit(self):
        with tempfile.TemporaryDirectory() as td:
            bad=Path(td)/"bad.json"; bad.write_text("{}",encoding="utf-8")
            done=subprocess.run(MODULE+["--manifest",str(bad)],cwd=ROOT,text=True,capture_output=True)
            self.assertEqual(done.returncode,2); self.assertEqual(json.loads(done.stderr)["status"],"FAIL")

    def test_evidence_is_machine_derived_and_rejects_bad_hash(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as td:
            output=Path(td)/"evidence.json"; relative="config/harbor-freight-backup-manifest.json"
            payload=generate_evidence(ROOT,output,[relative],{"count":12,"exit_code":0},{"tests_run":1,"exit_code":0,"result":"PASS"},"2026-01-01T00:00:00+00:00")
            item=payload["files"][0]; self.assertEqual(item["sha256"],sha256_file(ROOT/relative)); self.assertEqual(item["bytes"],(ROOT/relative).stat().st_size)
            self.assertEqual(len(item["sha256"]),64); self.assertTrue(all(c in "0123456789abcdef" for c in item["sha256"]))
            with self.assertRaises(ValueError): validate_sha256("not-a-real-hash")

    def test_evidence_generator_rejects_invalid_test_metadata(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as td:
            with self.assertRaises(ValueError): generate_evidence(ROOT,Path(td)/"x.json",["config/harbor-freight-backup-manifest.json"],{"count":-1,"exit_code":0},{})

if __name__ == "__main__": unittest.main()
