import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP_PATH = PROJECT_ROOT / "config" / "identity-bootstrap.json"
FILTER_PATH = PROJECT_ROOT / "deploy" / "open-webui" / "exact-tool-response-filter.py"
EXPECTED_SOURCE_HASHES = {
    "docs/identity/ORIGIN_RECORD.md": "09d21b9db47bd6ae153ff635d8e27a656e80fd569df3d7b1118992f34db1a8db",
    "docs/constitution/JOSIE_CONSTITUTION.md": "839cabf81c12a754cad0ef148ae379becf7cba0942e72e4861b7c22417d63247",
    "docs/identity/genesis/GENESIS_SESSION_001.yaml": "e116f79a16327fa96d42f6073d227a29a57ae73b5cec6c25d6d4889aaed68725",
    "docs/identity/genesis/CLAIM_LEDGER.yaml": "987933a31e92286a842cc4c91ec1b6d8adfbfbccdef0c0b8b98013cb495160ce",
}


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class IdentityBootstrapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("identity_bootstrap_filter_test", FILTER_PATH)
        cls.module = importlib.util.module_from_spec(spec)
        pydantic_stub = types.ModuleType("pydantic")
        pydantic_stub.BaseModel = object
        pydantic_stub.Field = lambda *, default: default
        with patch.dict(sys.modules, {"pydantic": pydantic_stub}):
            spec.loader.exec_module(cls.module)
        cls.module.IDENTITY_BOOTSTRAP_PATH = BOOTSTRAP_PATH
        cls.module.IDENTITY_SOURCE_ROOT = PROJECT_ROOT

    def test_projection_metadata_and_source_hashes_are_current(self):
        payload = json.loads(BOOTSTRAP_PATH.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["bootstrap_version"], "1.0.2")
        self.assertEqual(payload["status"], "reviewed_derived_projection")
        self.assertEqual(
            {source["path"]: source["sha256"] for source in payload["sources"]},
            EXPECTED_SOURCE_HASHES,
        )
        for relative, expected in EXPECTED_SOURCE_HASHES.items():
            self.assertEqual(file_sha256(PROJECT_ROOT / relative), expected)
        loaded = self.module._load_identity_bootstrap()
        self.assertEqual(loaded["version"], "1.0.2")
        self.assertEqual(len(loaded["sources"]), 4)

    def test_projection_stays_within_compact_context_budget(self):
        content = self.module._load_identity_bootstrap()["content"]
        self.assertGreaterEqual(len(content), 2_000)
        self.assertLessEqual(len(content), 12_000)
        approximate_tokens = round(len(content) / 4)
        self.assertGreaterEqual(approximate_tokens, 800)
        self.assertLessEqual(approximate_tokens, 1_500)

    def test_ordinary_chat_injects_for_both_front_doors_without_execution(self):
        for model_id in ("josie-qwen3-8b:1.0", "josie-local:1.0"):
            body = {
                "model": model_id,
                "messages": [
                    {"role": "system", "content": "existing operational policy"},
                    {"role": "user", "content": "Please introduce yourself briefly."},
                ],
            }
            with patch.dict(os.environ, {"JOSIE_IDENTITY_BOOTSTRAP_ENABLED": "true"}), patch.object(
                self.module, "_control_post"
            ) as execute, patch.object(self.module, "_record_history"):
                rendered = self.module.Filter().inlet(body)
            execute.assert_not_called()
            system = rendered["messages"][0]["content"]
            self.assertIn("<josie_identity_bootstrap version=\"1.0.2\">", system)
            self.assertIn("persistent, local-first AI orchestration system", system)
            self.assertEqual(
                rendered["metadata"]["josie_identity_bootstrap"]["status"], "available"
            )
            self.assertTrue(
                rendered["metadata"]["josie_identity_bootstrap"]["source_hashes_verified"]
            )

    def test_explicit_delegation_routes_are_not_modified(self):
        requests = (
            "Delegate Local: inspect only",
            "Delegate Local Code: inspect only",
            "Delegate Local status: local-test-0001",
            "Delegate Codex: inspect only",
            "Delegate Codex status: codex-test-0001",
        )
        for request in requests:
            body = {
                "model": "josie-qwen3-8b:1.0",
                "messages": [{"role": "user", "content": request}],
                "tool_ids": ["server:josie-subscription-seats"],
            }
            with patch.object(self.module, "_record_history"):
                rendered = self.module.Filter().inlet(body)
            self.assertNotIn("josie_identity_bootstrap", json.dumps(rendered))
            self.assertEqual(rendered["tool_ids"], [])

    def test_feature_flag_disables_injection_without_deleting_projection(self):
        body = {
            "model": "josie-qwen3-8b:1.0",
            "messages": [{"role": "user", "content": "Hello"}],
        }
        with patch.dict(os.environ, {"JOSIE_IDENTITY_BOOTSTRAP_ENABLED": "false"}), patch.object(
            self.module, "_record_history"
        ):
            rendered = self.module.Filter().inlet(body)
        self.assertNotIn("<josie_identity_bootstrap", json.dumps(rendered))
        self.assertEqual(rendered["metadata"]["josie_identity_bootstrap"]["status"], "disabled")
        self.assertTrue(BOOTSTRAP_PATH.is_file())

    def test_missing_or_invalid_projection_falls_back_to_nonexecuting_chat(self):
        body = {
            "model": "josie-local:1.0",
            "messages": [{"role": "user", "content": "Hello"}],
        }
        original_path = self.module.IDENTITY_BOOTSTRAP_PATH
        try:
            self.module.IDENTITY_BOOTSTRAP_PATH = PROJECT_ROOT / "config" / "absent-bootstrap.json"
            with patch.dict(os.environ, {"JOSIE_IDENTITY_BOOTSTRAP_ENABLED": "true"}), patch.object(
                self.module, "_record_history"
            ), patch.object(self.module, "_control_post") as execute:
                missing = self.module.Filter().inlet(body)
            execute.assert_not_called()
            self.assertEqual(
                missing["metadata"]["josie_identity_bootstrap"]["status"], "unavailable"
            )
            self.assertIn("Continue ordinary non-executing conversation", json.dumps(missing))

            with tempfile.TemporaryDirectory() as temp:
                invalid_path = Path(temp) / "bootstrap.json"
                invalid = json.loads(BOOTSTRAP_PATH.read_text(encoding="utf-8"))
                invalid["sources"][0]["sha256"] = "0" * 64
                invalid_path.write_text(json.dumps(invalid), encoding="utf-8")
                self.module.IDENTITY_BOOTSTRAP_PATH = invalid_path
                with patch.object(self.module, "_record_history"):
                    mismatch = self.module.Filter().inlet(body)
                self.assertEqual(
                    mismatch["metadata"]["josie_identity_bootstrap"]["status"],
                    "unavailable",
                )
        finally:
            self.module.IDENTITY_BOOTSTRAP_PATH = original_path

    def test_idempotent_setup_and_compose_bind_projection_read_only(self):
        configure = (PROJECT_ROOT / "deploy/open-webui/configure-model.py").read_text(
            encoding="utf-8"
        )
        compose = (PROJECT_ROOT / "deploy/compose.yaml").read_text(encoding="utf-8")
        self.assertIn("identity_bootstrap_status", configure)
        self.assertIn('MODEL_ID = "josie-local:1.0"', configure)
        self.assertIn('QWEN3_MODEL_ID = "josie-qwen3-8b:1.0"', configure)
        self.assertIn("identity-bootstrap.json:/opt/josie/identity-bootstrap.json:ro", compose)
        self.assertIn("JOSIE_IDENTITY_BOOTSTRAP_ENABLED", compose)
        for relative in EXPECTED_SOURCE_HASHES:
            self.assertIn(Path(relative).name, compose)


if __name__ == "__main__":
    unittest.main()
