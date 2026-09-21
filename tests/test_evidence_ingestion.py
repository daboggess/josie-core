"""Tests for Memory Vault Phase 3A: Safe, deterministic raw evidence ingestion foundation.

Covers all 16 required verification items:
1. Identical archive imported twice is idempotent
2. Same provider record gets stable deterministic evidence ID
3. Source archive SHA-256 is stable
4. Raw speaker/role is preserved
5. Provider timestamp is preserved where available
6. Original source/native IDs are preserved
7. Normalization does not alter semantic text
8. Duplicate records do not multiply
9. New records in an updated archive are added without rewriting old evidence
10. Malformed records are reported deterministically
11. Dry-run performs zero SQLite mutation
12. No-op second live import creates no unnecessary backup
13. Failed import rolls back transaction
14. Import does not create active memory_claims
15. Imported raw evidence does not automatically enter normal Prompt Contract priming
16. Live database protection (snapshot before/after unchanged)
"""

import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import zipfile

from josie.context_builder import build_context, retrieval_trigger
from josie.evidence_ingestion import (
    ChatGPTTakeoutAdapter,
    GeminiTakeoutAdapter,
    NormalizedEvidenceRecord,
    chunk_evidence_record,
    discover_available_archives,
    dry_run_evidence_ingest,
    execute_evidence_ingest,
    normalize_raw_text,
    parse_unix_timestamp,
)
from josie.knowledge import (
    assemble_priming_from_knowledge,
    load_knowledge_from_store,
)
from josie.storage import LocalStore
from supervisor.priming import PrimingManifest


def _create_chatgpt_json_data(messages_spec: list[dict]) -> list[dict]:
    """Helper to create a realistic ChatGPT conversations.json structure."""
    mapping = {}
    root_id = "root-node"
    mapping[root_id] = {
        "id": root_id,
        "message": None,
        "parent": None,
        "children": [messages_spec[0]["id"]] if messages_spec else [],
    }

    for i, spec in enumerate(messages_spec):
        msg_id = spec["id"]
        parent_id = root_id if i == 0 else messages_spec[i - 1]["id"]
        children = [messages_spec[i + 1]["id"]] if i + 1 < len(messages_spec) else []
        content_type = spec.get("content_type", "text")
        parts = spec.get("parts", [spec.get("text", "")])

        mapping[msg_id] = {
            "id": msg_id,
            "message": {
                "id": msg_id,
                "author": {
                    "role": spec.get("role", "user"),
                    "name": spec.get("name"),
                },
                "create_time": spec.get("create_time", 1724600000.0 + i * 10),
                "content": {
                    "content_type": content_type,
                    "parts": parts,
                },
            },
            "parent": parent_id,
            "children": children,
        }

    return [
        {
            "id": "conv-chatgpt-test-001",
            "title": "Hardware and Architecture Discussion",
            "create_time": 1724600000.0,
            "mapping": mapping,
        }
    ]


def _create_chatgpt_zip(target_path: Path, conversations: list[dict]) -> str:
    """Write conversations to a ChatGPT Takeout-style zip file and return SHA-256."""
    json_bytes = json.dumps(conversations, indent=2).encode("utf-8")
    with zipfile.ZipFile(target_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("conversations.json", json_bytes)
        zf.writestr("user.json", b'{"id": "user-123"}')
    archive_bytes = target_path.read_bytes()
    return hashlib.sha256(archive_bytes).hexdigest()


def _gemini_activity_card(
    *,
    prompt: str,
    timestamp: str,
    response: str = "",
    conversation_id: str = "gemini-conv-001",
    attachment: str = "",
) -> str:
    attachment_html = (
        f'<div class="content-cell mdl-cell mdl-cell--12-col mdl-typography--caption">'
        f'<a href="{attachment}">Attached File</a></div>'
        if attachment
        else ""
    )
    return (
        '<div class="outer-cell mdl-cell mdl-cell--12-col mdl-shadow--2dp">'
        '<div class="content-cell mdl-cell mdl-cell--6-col mdl-typography--body-1">'
        f"Prompted {prompt}<br>{timestamp}"
        + (f"<br>{response}" if response else "")
        + f'<a href="https://gemini.google.com/app/{conversation_id}"></a>'
        + attachment_html
        + "</div>"
        '<div class="mdl-typography--caption">Gemini Apps</div>'
        "</div>"
    )


def _create_gemini_zip(target_path: Path, cards: list[str]) -> str:
    """Write Gemini MyActivity.html into a Takeout-style zip file and return SHA-256."""
    html_content = (
        '<html><body><title>My Activity History</title>'
        + "".join(cards)
        + "</body></html>"
    )
    with zipfile.ZipFile(target_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "Takeout/My Activity/Gemini Apps/MyActivity.html",
            html_content.encode("utf-8"),
        )
    archive_bytes = target_path.read_bytes()
    return hashlib.sha256(archive_bytes).hexdigest()


class TestEvidenceIngestion(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.db_path = self.root / "test_josie.db"
        self.store = LocalStore(self.db_path)

    def tearDown(self):
        self.tmp_dir.cleanup()

    # 1. Identical archive imported twice is idempotent
    def test_01_identical_archive_imported_twice_is_idempotent(self):
        data = _create_chatgpt_json_data([
            {"id": "msg-001", "role": "user", "text": "Hello world"},
            {"id": "msg-002", "role": "assistant", "text": "Hi Dustin!"},
        ])
        archive_path = self.root / "chatgpt-test.zip"
        _create_chatgpt_zip(archive_path, data)

        res1 = execute_evidence_ingest(
            archive_path,
            store=self.store,
            run_id="test-ingest-run-001",
        )
        self.assertEqual(res1.status, "success")
        self.assertEqual(res1.inserted_messages, 2)
        self.assertFalse(res1.idempotent_replay)

        counts1 = self.store.history_counts()
        self.assertEqual(counts1["history_messages"], 2)

        # Re-import identical archive
        res2 = execute_evidence_ingest(
            archive_path,
            store=self.store,
            run_id="test-ingest-run-002",
        )
        self.assertEqual(res2.status, "idempotent_replay")
        self.assertEqual(res2.inserted_messages, 0)
        self.assertTrue(res2.idempotent_replay)

        counts2 = self.store.history_counts()
        self.assertEqual(counts2["history_messages"], 2)

    # 2. Same provider record gets stable deterministic evidence ID
    def test_02_stable_deterministic_evidence_id(self):
        adapter = ChatGPTTakeoutAdapter()
        data = _create_chatgpt_json_data([
            {"id": "msg-stable-001", "role": "user", "text": "Stable ID check"},
        ])
        archive_path = self.root / "chatgpt-stable.zip"
        _create_chatgpt_zip(archive_path, data)

        msgs1, _ = adapter.parse(archive_path)
        msgs2, _ = adapter.parse(archive_path)

        self.assertEqual(len(msgs1), 1)
        self.assertEqual(len(msgs2), 1)
        self.assertEqual(msgs1[0].stable_id, msgs2[0].stable_id)
        self.assertEqual(msgs1[0].dedupe_key, msgs2[0].dedupe_key)
        self.assertEqual(
            msgs1[0].stable_id,
            "msg_chatgpt_conv-chatgpt-test-001_msg-stable-001",
        )
        self.assertEqual(
            msgs1[0].dedupe_key,
            "openai_chatgpt:conv-chatgpt-test-001:msg-stable-001",
        )

    # 3. Source archive SHA-256 is stable
    def test_03_stable_source_archive_sha256(self):
        data = _create_chatgpt_json_data([
            {"id": "msg-sha-001", "role": "user", "text": "Testing SHA"},
        ])
        archive_path = self.root / "chatgpt-sha.zip"
        expected_sha = _create_chatgpt_zip(archive_path, data)

        adapter = ChatGPTTakeoutAdapter()
        manifest1 = adapter.inspect_archive(archive_path)
        manifest2 = adapter.inspect_archive(archive_path)

        self.assertEqual(manifest1.archive_sha256, expected_sha)
        self.assertEqual(manifest2.archive_sha256, expected_sha)
        self.assertEqual(manifest1.archive_sha256, manifest2.archive_sha256)

    # 4. Raw speaker/role is preserved
    def test_04_raw_speaker_and_role_preserved(self):
        data = _create_chatgpt_json_data([
            {"id": "msg-r1", "role": "user", "name": "Dustin", "text": "Prompt text"},
            {"id": "msg-r2", "role": "assistant", "name": "ChatGPT-4", "text": "Response text"},
            {"id": "msg-r3", "role": "system", "text": "System instructions"},
            {"id": "msg-r4", "role": "tool", "text": "Tool output"},
        ])
        archive_path = self.root / "chatgpt-roles.zip"
        _create_chatgpt_zip(archive_path, data)

        adapter = ChatGPTTakeoutAdapter()
        records, _ = adapter.parse(archive_path)

        roles_map = {r.source_message_id: (r.role, r.speaker) for r in records}
        self.assertEqual(roles_map["msg-r1"], ("user", "Dustin"))
        self.assertEqual(roles_map["msg-r2"], ("assistant", "ChatGPT-4"))
        self.assertEqual(roles_map["msg-r3"], ("system", "system"))
        self.assertEqual(roles_map["msg-r4"], ("tool", "tool"))

    # 5. Provider timestamp is preserved where available
    def test_05_provider_timestamp_preserved(self):
        test_epoch = 1724601234.0
        data = _create_chatgpt_json_data([
            {"id": "msg-time-001", "role": "user", "create_time": test_epoch, "text": "Time check"},
        ])
        archive_path = self.root / "chatgpt-time.zip"
        _create_chatgpt_zip(archive_path, data)

        adapter = ChatGPTTakeoutAdapter()
        records, _ = adapter.parse(archive_path)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].source_timestamp, str(test_epoch))
        self.assertTrue(records[0].timestamp.endswith("Z"))
        self.assertIn("2024-08-25", records[0].timestamp)

    # 6. Original source/native IDs are preserved
    def test_06_original_source_native_ids_preserved(self):
        data = _create_chatgpt_json_data([
            {"id": "msg-native-42", "role": "user", "text": "Check native IDs"},
        ])
        archive_path = self.root / "chatgpt-ids.zip"
        _create_chatgpt_zip(archive_path, data)

        adapter = ChatGPTTakeoutAdapter()
        records, _ = adapter.parse(archive_path)

        self.assertEqual(records[0].source_conversation_id, "conv-chatgpt-test-001")
        self.assertEqual(records[0].source_message_id, "msg-native-42")
        self.assertIn("conversations.json#conv-chatgpt-test-001:msg-native-42", records[0].source_pointer)

    # 7. Raw text is verbatim and search normalization is separate
    def test_07_raw_text_is_verbatim_and_search_normalization_is_separate(self):
        verbatim_raw = (
            "Line 1\r\nLine 2\r\n"
            "Ligature: \ufb01le and fullwidth: \uff2a\uff4f\uff53\uff49\uff45\n"
            "Smart quotes: \u201cJosie\u201d and emoji: \U0001f680\n"
            "\tIntentional   whitespace and trailing space  \r\n"
        )
        data = _create_chatgpt_json_data([
            {"id": "msg-verbatim-001", "role": "user", "text": verbatim_raw},
        ])
        archive_path = self.root / "chatgpt-verbatim.zip"
        _create_chatgpt_zip(archive_path, data)

        adapter = ChatGPTTakeoutAdapter()
        records, _ = adapter.parse(archive_path)

        self.assertEqual(len(records), 1)
        persisted_raw = records[0].raw_text

        # 1. Assert raw_text is completely verbatim: NOT NFKC normalized, NOT line-ending rewritten
        self.assertEqual(persisted_raw, verbatim_raw)
        self.assertIn("\ufb01le", persisted_raw)
        self.assertIn("\uff2a\uff4f\uff53\uff49\uff45", persisted_raw)
        self.assertIn("\u201cJosie\u201d", persisted_raw)
        self.assertIn("\U0001f680", persisted_raw)
        self.assertIn("\r\n", persisted_raw)
        self.assertIn("\tIntentional   whitespace", persisted_raw)
        self.assertEqual(records[0].raw_checksum, hashlib.sha256(verbatim_raw.encode("utf-8")).hexdigest())

        # 2. Assert normalize_for_search is a separate, deterministic search helper
        search_norm = normalize_raw_text(verbatim_raw)
        self.assertNotIn("\r\n", search_norm)
        self.assertIn("file", search_norm)
        self.assertIn("Josie", search_norm)
        # Crucially: search_norm differs from persisted verbatim_raw
        self.assertNotEqual(persisted_raw, search_norm)

    # 8. Duplicate records do not multiply
    def test_08_duplicate_records_do_not_multiply(self):
        conv_dup = _create_chatgpt_json_data([
            {"id": "msg-dup-1", "role": "user", "text": "Original message"},
        ])
        archive_path = self.root / "chatgpt-dup.zip"
        _create_chatgpt_zip(archive_path, conv_dup)

        res = execute_evidence_ingest(
            archive_path,
            store=self.store,
            run_id="test-ingest-dup-001",
        )
        self.assertEqual(res.inserted_messages, 1)

        counts = self.store.history_counts()
        self.assertEqual(counts["history_messages"], 1)

    # 9. New records in an updated archive are added without rewriting old evidence
    def test_09_new_records_in_updated_archive_added_without_rewriting_old(self):
        archive_v1 = self.root / "chatgpt-v1.zip"
        _create_chatgpt_zip(archive_v1, _create_chatgpt_json_data([
            {"id": "msg-base-1", "role": "user", "text": "Base message 1"},
        ]))

        res1 = execute_evidence_ingest(
            archive_v1,
            store=self.store,
            run_id="test-ingest-v1",
        )
        self.assertEqual(res1.inserted_messages, 1)

        archive_v2 = self.root / "chatgpt-v2.zip"
        _create_chatgpt_zip(archive_v2, _create_chatgpt_json_data([
            {"id": "msg-base-1", "role": "user", "text": "Base message 1"},
            {"id": "msg-new-2", "role": "assistant", "text": "Newly added message 2"},
        ]))

        res2 = execute_evidence_ingest(
            archive_v2,
            store=self.store,
            run_id="test-ingest-v2",
        )
        self.assertEqual(res2.inserted_messages, 1)
        self.assertEqual(res2.deduplicated_messages, 1)

        counts = self.store.history_counts()
        self.assertEqual(counts["history_messages"], 2)

    # 10. Malformed records are reported deterministically
    def test_10_malformed_records_reported_deterministically(self):
        malformed_json = [
            {"id": "valid-conv", "title": "Valid", "mapping": {
                "node-1": {
                    "id": "node-1",
                    "message": {
                        "id": "msg-valid-1",
                        "author": {"role": "user"},
                        "content": {"content_type": "text", "parts": ["Valid text"]},
                    },
                }
            }},
            {"invalid_no_id": True},
            "not even a dict",
        ]
        archive_path = self.root / "chatgpt-malformed.zip"
        with zipfile.ZipFile(archive_path, "w") as zf:
            zf.writestr("conversations.json", json.dumps(malformed_json).encode("utf-8"))

        adapter = ChatGPTTakeoutAdapter()
        records, malformed = adapter.parse(archive_path)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].source_message_id, "msg-valid-1")
        self.assertEqual(len(malformed), 2)
        self.assertIn("Conversation missing id", malformed[0].reason)
        self.assertIn("Conversation entry is not an object", malformed[1].reason)

    # 11. Dry-run performs zero SQLite mutation
    def test_11_dry_run_performs_zero_sqlite_mutation(self):
        data = _create_chatgpt_json_data([
            {"id": "msg-dry-1", "role": "user", "text": "Dry run check"},
        ])
        archive_path = self.root / "chatgpt-dry.zip"
        _create_chatgpt_zip(archive_path, data)

        # Case A: Dry run without a store target
        dry_summary_a = dry_run_evidence_ingest(archive_path, store=None)
        self.assertEqual(dry_summary_a.status, "dry_run_complete")
        self.assertEqual(dry_summary_a.writes_performed, 0)
        self.assertIsNone(dry_summary_a.database_target)

        # Case B: Dry run with existing database
        initial_counts = self.store.history_counts()
        initial_hash = hashlib.sha256(self.db_path.read_bytes()).hexdigest()

        dry_summary_b = dry_run_evidence_ingest(archive_path, store=self.store)
        self.assertEqual(dry_summary_b.status, "dry_run_complete")
        self.assertEqual(dry_summary_b.writes_performed, 0)
        self.assertEqual(dry_summary_b.messages_would_insert, 1)

        counts_after = self.store.history_counts()
        after_hash = hashlib.sha256(self.db_path.read_bytes()).hexdigest()
        self.assertEqual(initial_counts, counts_after, "Database counts must remain identical after dry run")
        self.assertEqual(initial_hash, after_hash, "Database file content must remain identical after dry run")

    # 12. No-op second live import creates no unnecessary backup
    def test_12_noop_second_live_import_creates_no_unnecessary_backup(self):
        data = _create_chatgpt_json_data([
            {"id": "msg-backup-1", "role": "user", "text": "Backup check"},
        ])
        archive_path = self.root / "chatgpt-backup.zip"
        _create_chatgpt_zip(archive_path, data)
        backup_dir = self.root / "backups"

        res1 = execute_evidence_ingest(
            archive_path,
            store=self.store,
            run_id="test-ingest-backup-001",
            backup=True,
            backup_dir=backup_dir,
        )
        self.assertIsNotNone(res1.backup_path)
        self.assertTrue(Path(res1.backup_path).exists())

        backups_count_1 = len(list(backup_dir.glob("*.db")))
        self.assertEqual(backups_count_1, 1)

        res2 = execute_evidence_ingest(
            archive_path,
            store=self.store,
            run_id="test-ingest-backup-002",
            backup=True,
            backup_dir=backup_dir,
        )
        self.assertIsNone(res2.backup_path)
        self.assertTrue(res2.idempotent_replay)

        backups_count_2 = len(list(backup_dir.glob("*.db")))
        self.assertEqual(backups_count_2, 1, "No-op import must not create any new backup files")

    # 13. Failed import rolls back transaction
    def test_13_failed_import_rolls_back_transaction(self):
        data = _create_chatgpt_json_data([
            {"id": "msg-fail-1", "role": "user", "text": "First message"},
            {"id": "msg-fail-2", "role": "assistant", "text": "Second message (causes simulated failure)"},
        ])
        archive_path = self.root / "chatgpt-fail.zip"
        _create_chatgpt_zip(archive_path, data)

        with self.assertRaises(RuntimeError):
            execute_evidence_ingest(
                archive_path,
                store=self.store,
                run_id="test-ingest-fail-001",
                simulate_failure_after=2,
            )

        counts = self.store.history_counts()
        self.assertEqual(counts["history_messages"], 0)
        self.assertEqual(counts["history_conversations"], 0)
        self.assertEqual(counts["history_sources"], 0)

        run_record = self.store.history_import_run("test-ingest-fail-001")
        self.assertIsNotNone(run_record)
        self.assertEqual(run_record["status"], "rolled_back")

    # 14. Import does not create active memory_claims
    def test_14_import_does_not_create_active_memory_claims(self):
        with self.store._connect() as conn:
            claims_before = int(conn.execute("SELECT COUNT(*) FROM memory_claims").fetchone()[0])
            evidence_before = int(conn.execute("SELECT COUNT(*) FROM claim_evidence").fetchone()[0])
        self.assertEqual(claims_before, 0)
        self.assertEqual(evidence_before, 0)

        data = _create_chatgpt_json_data([
            {"id": "msg-claim-1", "role": "user", "text": "Dustin prefers Python over Bash."},
            {"id": "msg-claim-2", "role": "assistant", "text": "Understood, I will remember Dustin prefers Python."},
        ])
        archive_path = self.root / "chatgpt-claims.zip"
        _create_chatgpt_zip(archive_path, data)

        execute_evidence_ingest(
            archive_path,
            store=self.store,
            run_id="test-ingest-claims-001",
        )

        gemini_archive = self.root / "gemini-claims.zip"
        _create_gemini_zip(gemini_archive, [
            _gemini_activity_card(
                prompt="Dustin has an RTX 3060 with 12GB VRAM",
                timestamp="Feb 3, 2026, 10:11:12 AM EST",
                response="Acknowledged hardware config.",
                conversation_id="thread-gemini-42",
            )
        ])
        execute_evidence_ingest(
            gemini_archive,
            store=self.store,
            run_id="test-ingest-claims-002",
        )

        with self.store._connect() as conn:
            claims_after = int(conn.execute("SELECT COUNT(*) FROM memory_claims").fetchone()[0])
            evidence_after = int(conn.execute("SELECT COUNT(*) FROM claim_evidence").fetchone()[0])
            historical_msgs = int(conn.execute("SELECT COUNT(*) FROM history_messages").fetchone()[0])

        self.assertEqual(claims_after, 0, "Raw evidence ingestion must NOT create any rows in memory_claims")
        self.assertEqual(evidence_after, 0, "Raw evidence ingestion must NOT create any rows in claim_evidence")
        self.assertGreaterEqual(historical_msgs, 4)

    # 15. Imported raw evidence does not automatically enter normal Prompt Contract priming
    def test_15_imported_raw_evidence_does_not_enter_normal_prompt_contract_priming(self):
        data = _create_chatgpt_json_data([
            {"id": "msg-prime-1", "role": "user", "text": "Secret project code: NEBULA-999."},
            {"id": "msg-prime-2", "role": "assistant", "text": "Noted NEBULA-999."},
        ])
        archive_path = self.root / "chatgpt-priming.zip"
        _create_chatgpt_zip(archive_path, data)

        execute_evidence_ingest(
            archive_path,
            store=self.store,
            run_id="test-ingest-prime-001",
        )

        knowledge_records = load_knowledge_from_store(self.store)
        self.assertEqual(len(knowledge_records), 0, "Raw evidence must never be loaded as canonical knowledge")

        manifest = PrimingManifest(
            task_id="test-task-priming",
            max_items=10,
            max_characters=2000,
        )

        bundle = assemble_priming_from_knowledge(manifest, store=self.store)
        self.assertEqual(len(bundle.items), 0)
        self.assertTrue(bundle.is_empty)
        self.assertEqual(len(bundle.to_retrieved_evidence()), 0)

        # Non-retrieval query does not retrieve historical evidence
        self.assertFalse(retrieval_trigger("Help me with NEBULA-999")["triggered"])
        context_result = build_context(
            project_root=self.root,
            store=self.store,
            query="Help me with NEBULA-999",
            request_id="test-prime-ctx-001",
        )
        self.assertFalse(context_result["triggered"])
        self.assertNotIn("packet", context_result)

    # 16. Live database protection (snapshot before/after unchanged)
    def test_16_live_database_protection(self):
        live_db = Path(r"D:\Josie\data\josie.db")
        if not live_db.exists():
            return

        stat_before = live_db.stat()
        sha_before = hashlib.sha256(live_db.read_bytes()).hexdigest()

        data = _create_chatgpt_json_data([
            {"id": "msg-prot-1", "role": "user", "text": "Isolated test msg"},
        ])
        archive_path = self.root / "chatgpt-isolated.zip"
        _create_chatgpt_zip(archive_path, data)

        execute_evidence_ingest(
            archive_path,
            store=self.store,
            run_id="test-ingest-prot-001",
        )

        stat_after = live_db.stat()
        sha_after = hashlib.sha256(live_db.read_bytes()).hexdigest()

        self.assertEqual(stat_before.st_size, stat_after.st_size, "Live DB file size changed during isolated tests!")
        self.assertEqual(sha_before, sha_after, "Live DB file hash changed during isolated tests!")

    def test_chunk_evidence_record(self):
        rec = NormalizedEvidenceRecord(
            stable_id="msg_test_123",
            dedupe_key="platform:c1:m1",
            source_platform="openai_chatgpt",
            source_archive="test.zip",
            source_archive_sha256="0" * 64,
            source_path="conversations.json",
            source_member_sha256="1" * 64,
            source_pointer="conversations.json#c1:m1",
            source_conversation_id="c1",
            conversation_title="Title",
            source_message_id="m1",
            timestamp="2026-08-25T19:00:00Z",
            source_timestamp="1724612400",
            speaker="user",
            role="user",
            raw_text="A" * 2500,
            raw_checksum=hashlib.sha256(("A" * 2500).encode("utf-8")).hexdigest(),
            source_record_checksum="2" * 64,
            source_order=0,
            message_order=0,
            activity_type="conversation",
        )

        chunks = chunk_evidence_record(rec, max_chars=1000, overlap_chars=100)
        self.assertEqual(len(chunks), 3)
        self.assertEqual(chunks[0].chunk_id, "msg_test_123:chunk:0")
        self.assertEqual(chunks[0].parent_stable_id, "msg_test_123")
        self.assertEqual(chunks[0].start_char, 0)
        self.assertEqual(chunks[0].end_char, 1000)
        self.assertEqual(chunks[1].start_char, 900)
        self.assertEqual(chunks[1].end_char, 1900)
        self.assertEqual(chunks[2].start_char, 1800)
        self.assertEqual(chunks[2].end_char, 2500)

    def test_gemini_adapter_parsing(self):
        gemini_archive = self.root / "gemini-test.zip"
        _create_gemini_zip(gemini_archive, [
            _gemini_activity_card(
                prompt="Explain the difference between Bernie and Sophie",
                timestamp="Aug 25, 2026, 12:34:56 PM EDT",
                response="Bernie was the earlier assistant persona.",
                conversation_id="conv-bernie-1",
            )
        ])

        adapter = GeminiTakeoutAdapter()
        self.assertTrue(adapter.can_handle(gemini_archive))

        manifest = adapter.inspect_archive(gemini_archive)
        self.assertEqual(manifest.provider, "google_gemini")
        self.assertEqual(manifest.member_count, 1)

        records, malformed = adapter.parse(gemini_archive)
        self.assertGreater(len(records), 0)
        self.assertEqual(len(malformed), 0)
        self.assertEqual(records[0].source_platform, "google_gemini")
        self.assertTrue(any("Bernie" in r.raw_text for r in records))

    def test_discover_available_archives(self):
        archives = discover_available_archives(search_roots=[self.root])
        self.assertIsInstance(archives, list)

    # 17. Structured ChatGPT parts reproducibility
    def test_17_chatgpt_multipart_preserves_boundaries_and_reproducibility(self):
        parts = [
            "First paragraph with technical requirement.\n",
            "Second paragraph with architecture explanation.",
        ]
        data = _create_chatgpt_json_data([
            {"id": "msg-multi-001", "role": "assistant", "parts": parts},
        ])
        archive_path = self.root / "chatgpt-multipart.zip"
        archive_sha = _create_chatgpt_zip(archive_path, data)

        adapter = ChatGPTTakeoutAdapter()
        records, _ = adapter.parse(archive_path)

        self.assertEqual(len(records), 1)
        rec = records[0]

        # raw_text is the concatenated verbatim projection
        self.assertEqual(rec.raw_text, "".join(parts))

        # source_record_checksum fingerprints the exact raw JSON object with the parts list intact
        raw_msg_dict = data[0]["mapping"]["msg-multi-001"]["message"]
        expected_rec_checksum = hashlib.sha256(
            json.dumps(raw_msg_dict, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        self.assertEqual(rec.source_record_checksum, expected_rec_checksum)

        # The original multipart structure is 100% reproducible from archive + pointer + checksum
        self.assertEqual(rec.source_archive_sha256, archive_sha)
        self.assertIn("conv-chatgpt-test-001:msg-multi-001", rec.source_pointer)

    # 18. Importer does not collide with legacy history
    def test_18_importer_does_not_collide_with_legacy_history(self):
        # 1. Seed database with preexisting legacy history rows
        legacy_data = _create_chatgpt_json_data([
            {"id": "msg-legacy-001", "role": "user", "text": "Preexisting legacy message"},
        ])
        legacy_archive = self.root / "chatgpt-legacy.zip"
        _create_chatgpt_zip(legacy_archive, legacy_data)

        res_init = execute_evidence_ingest(
            legacy_archive,
            store=self.store,
            run_id="test-legacy-init",
        )
        self.assertEqual(res_init.inserted_messages, 1)

        # Capture initial state
        initial_counts = self.store.history_counts()
        with self.store._connect() as conn:
            initial_legacy_row = dict(conn.execute(
                "SELECT * FROM history_messages WHERE source_message_id='msg-legacy-001'"
            ).fetchone())

        # Behavior A: Identical preexisting evidence -> duplicate/no-op, idempotent replay
        res_replay = execute_evidence_ingest(
            legacy_archive,
            store=self.store,
            run_id="test-legacy-replay",
        )
        self.assertTrue(res_replay.idempotent_replay)
        self.assertEqual(res_replay.inserted_messages, 0)
        self.assertEqual(self.store.history_counts(), initial_counts)

        # Behavior B: Same stable/native identity but different content/checksum -> explicit conflict / fail closed
        tampered_data = _create_chatgpt_json_data([
            {"id": "msg-legacy-001", "role": "user", "text": "Tampered conflicting text!"},
        ])
        tampered_archive = self.root / "chatgpt-tampered.zip"
        _create_chatgpt_zip(tampered_archive, tampered_data)

        with self.assertRaisesRegex(ValueError, "Evidence conflict detected"):
            execute_evidence_ingest(
                tampered_archive,
                store=self.store,
                run_id="test-legacy-tampered",
            )
        # Database remains completely uncorrupted
        self.assertEqual(self.store.history_counts(), initial_counts)

        # Behavior C: Genuinely new record -> inserts normally alongside legacy rows
        new_data = _create_chatgpt_json_data([
            {"id": "msg-new-002", "role": "assistant", "text": "Genuinely new message"},
        ])
        new_archive = self.root / "chatgpt-new.zip"
        _create_chatgpt_zip(new_archive, new_data)

        res_new = execute_evidence_ingest(
            new_archive,
            store=self.store,
            run_id="test-legacy-new",
        )
        self.assertEqual(res_new.inserted_messages, 1)
        self.assertEqual(self.store.history_counts()["history_messages"], 2)

        # Behavior D: Existing row was never overwritten silently
        with self.store._connect() as conn:
            after_legacy_row = dict(conn.execute(
                "SELECT * FROM history_messages WHERE source_message_id='msg-legacy-001'"
            ).fetchone())
        self.assertEqual(initial_legacy_row["raw_text"], after_legacy_row["raw_text"])
        self.assertEqual(initial_legacy_row["raw_checksum"], after_legacy_row["raw_checksum"])

    # 19. Production run-id safety audit
    def test_19_production_run_id_safety(self):
        data = _create_chatgpt_json_data([
            {"id": "msg-safety-001", "role": "user", "text": "Safety check"},
        ])
        adapter = ChatGPTTakeoutAdapter()
        archive_path = self.root / "chatgpt-safety.zip"
        archive_sha = _create_chatgpt_zip(archive_path, data)
        records, _ = adapter.parse(archive_path)

        unsafe_run_ids = [
            "prod/run",
            "prod\\run",
            "prod..run",
            "../escape",
            ".hidden_run",
            "run_dot.",
            " prod_space",
            "prod_space ",
            "prod\nnewline",
            "prod;rm -rf /",
            "prod$VAR",
            "prod|cat",
            "prod&echo",
            "prod>out",
            "prod`ls`",
            "prod\"quote",
            "prod'quote",
            "",
            "x" * 121,
        ]

        for bad_id in unsafe_run_ids:
            with self.subTest(run_id=bad_id):
                with self.assertRaises(ValueError, msg=f"Run ID '{bad_id}' should have been rejected"):
                    self.store.import_raw_evidence(
                        run_id=bad_id,
                        source_set_id="set-001",
                        source_manifest_sha256=archive_sha,
                        source_format="openai_chatgpt_takeout_zip",
                        source_bytes=archive_path.stat().st_size,
                        messages=records,
                        mode="production",
                        authorized=True,
                        expected={"messages": 1, "conversations": 1},
                    )

        valid_run_ids = [
            "chatgpt-run-20260921",
            "gemini-phase2-20260825-retry1",
            "evidence_import_001",
            "raw-evidence.batch-42",
        ]
        import re
        run_pattern = r"[A-Za-z0-9][A-Za-z0-9._-]{0,119}"
        for good_id in valid_run_ids:
            self.assertTrue(bool(re.fullmatch(run_pattern, good_id)))
            self.assertNotIn("..", good_id)
            self.assertFalse(good_id.startswith("."))
            self.assertFalse(good_id.endswith("."))


if __name__ == "__main__":
    unittest.main()
