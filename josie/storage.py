"""Local SQLite persistence for conversations, memories, and task records."""

from __future__ import annotations

import json
import hashlib
import re
import sqlite3
from contextlib import closing, contextmanager
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from urllib.parse import urlparse


class LocalStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY, created_at TEXT NOT NULL,
                    speaker TEXT NOT NULL, content TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, content TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY, created_at TEXT NOT NULL,
                    description TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'complete'))
                );
                CREATE TABLE IF NOT EXISTS approvals (
                    id INTEGER PRIMARY KEY, created_at TEXT NOT NULL,
                    description TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'approved', 'denied'))
                );
                CREATE TABLE IF NOT EXISTS audit (
                    id INTEGER PRIMARY KEY, created_at TEXT NOT NULL,
                    event TEXT NOT NULL, detail TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, due_at TEXT NOT NULL,
                    description TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'delivered'))
                );
                CREATE TABLE IF NOT EXISTS ledger_entries (
                    id INTEGER PRIMARY KEY, created_at TEXT NOT NULL,
                    basis TEXT NOT NULL CHECK (basis IN ('actual', 'estimated')),
                    category TEXT NOT NULL CHECK (
                        category IN ('revenue', 'expense', 'api_cost', 'electricity', 'savings')
                    ),
                    amount_cents INTEGER NOT NULL CHECK (amount_cents >= 0),
                    description TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS provenance_records (
                    id INTEGER PRIMARY KEY, created_at TEXT NOT NULL,
                    source TEXT NOT NULL, statement TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'unverified'
                    CHECK (status IN ('unverified', 'confirmed', 'rejected'))
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY, created_at TEXT NOT NULL,
                    handler TEXT NOT NULL, payload_json TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','running','succeeded','failed','review_required')),
                    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
                    max_attempts INTEGER NOT NULL CHECK (max_attempts BETWEEN 1 AND 3),
                    result_json TEXT, last_error TEXT
                );
                CREATE TABLE IF NOT EXISTS repair_proposals (
                    id INTEGER PRIMARY KEY, created_at TEXT NOT NULL,
                    job_id INTEGER NOT NULL, failure TEXT NOT NULL,
                    proposal TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'review_required'
                    CHECK (status IN ('review_required','accepted','rejected')),
                    FOREIGN KEY(job_id) REFERENCES jobs(id)
                );
                CREATE TABLE IF NOT EXISTS memory_changes (
                    id INTEGER PRIMARY KEY, created_at TEXT NOT NULL,
                    memory_id INTEGER NOT NULL,
                    action TEXT NOT NULL CHECK (action IN ('correct','delete','restore')),
                    replacement_content TEXT,
                    approval_id INTEGER NOT NULL UNIQUE,
                    status TEXT NOT NULL DEFAULT 'pending_review'
                    CHECK (status IN ('pending_review','applied','denied')),
                    applied_at TEXT,
                    original_content TEXT,
                    FOREIGN KEY(memory_id) REFERENCES memories(id),
                    FOREIGN KEY(approval_id) REFERENCES approvals(id)
                );
                CREATE TABLE IF NOT EXISTS model_proposals (
                    id INTEGER PRIMARY KEY, created_at TEXT NOT NULL,
                    user_input TEXT NOT NULL, model TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'review_required'
                    CHECK (status IN ('review_required','accepted','rejected'))
                );
                CREATE TABLE IF NOT EXISTS external_proposals (
                    id INTEGER PRIMARY KEY, received_at TEXT NOT NULL,
                    external_id TEXT NOT NULL UNIQUE, external_created_at TEXT NOT NULL,
                    source TEXT NOT NULL CHECK (source='openwebui'),
                    kind TEXT NOT NULL CHECK (kind IN ('health_check','memory_export','restore_drill')),
                    summary TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'review_required'
                    CHECK (status IN ('review_required','accepted','rejected'))
                );
                CREATE TABLE IF NOT EXISTS economic_opportunities (
                    id INTEGER PRIMARY KEY, created_at TEXT NOT NULL,
                    title TEXT NOT NULL, source TEXT NOT NULL,
                    estimated_revenue_cents INTEGER NOT NULL
                    CHECK (estimated_revenue_cents >= 0),
                    estimated_cost_cents INTEGER NOT NULL
                    CHECK (estimated_cost_cents >= 0),
                    estimated_hours_milli INTEGER NOT NULL
                    CHECK (estimated_hours_milli > 0),
                    risk TEXT NOT NULL CHECK (risk IN ('low','medium','high')),
                    notes TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'research_only'
                    CHECK (status IN ('research_only','rejected','approved_for_human_review')),
                    external_activity INTEGER NOT NULL DEFAULT 0
                    CHECK (external_activity = 0),
                    action_authorized INTEGER NOT NULL DEFAULT 0
                    CHECK (action_authorized = 0)
                );
                CREATE TABLE IF NOT EXISTS deal_candidates (
                    candidate_id INTEGER PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    title TEXT NOT NULL,
                    source_reference TEXT NOT NULL,
                    source_kind TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    total_acquisition_cents INTEGER NOT NULL
                    CHECK (total_acquisition_cents > 0),
                    research_score_milli INTEGER NOT NULL
                    CHECK (research_score_milli >= 0 AND research_score_milli <= 100000),
                    evidence_status TEXT NOT NULL
                    CHECK (evidence_status IN ('verified_for_analysis','verification_required')),
                    recommendation TEXT NOT NULL
                    CHECK (recommendation IN ('candidate_for_human_review','watchlist',
                    'low_priority','verify_before_review','high_risk_hold','reject_incompatible')),
                    result_json TEXT NOT NULL,
                    external_activity INTEGER NOT NULL DEFAULT 0
                    CHECK (external_activity = 0),
                    action_authorized INTEGER NOT NULL DEFAULT 0
                    CHECK (action_authorized = 0),
                    purchase_authorized INTEGER NOT NULL DEFAULT 0
                    CHECK (purchase_authorized = 0),
                    capability_change TEXT NOT NULL DEFAULT 'none'
                    CHECK (capability_change = 'none')
                );
                CREATE TABLE IF NOT EXISTS deal_discoveries (
                    discovery_id INTEGER PRIMARY KEY,
                    source_id TEXT NOT NULL CHECK (source_id = 'ebay_browse_api'),
                    external_item_id TEXT NOT NULL,
                    deduplication_key TEXT NOT NULL UNIQUE,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    observation_count INTEGER NOT NULL DEFAULT 1
                    CHECK (observation_count >= 1),
                    title TEXT NOT NULL,
                    item_url TEXT NOT NULL,
                    ask_price_cents INTEGER NOT NULL CHECK (ask_price_cents > 0),
                    shipping_cents INTEGER CHECK (shipping_cents >= 0),
                    shipping_known INTEGER NOT NULL CHECK (shipping_known IN (0,1)),
                    tax_known INTEGER NOT NULL DEFAULT 0 CHECK (tax_known = 0),
                    total_acquisition_cents INTEGER CHECK (total_acquisition_cents IS NULL),
                    condition TEXT NOT NULL
                    CHECK (condition IN ('new','used_good','used_unknown','parts_only')),
                    seller_risk TEXT NOT NULL CHECK (seller_risk IN ('low','medium','high')),
                    evidence_status TEXT NOT NULL
                    CHECK (evidence_status = 'unverified_adapter_input'),
                    normalized_json TEXT NOT NULL,
                    scoring_ready INTEGER NOT NULL DEFAULT 0 CHECK (scoring_ready = 0),
                    external_activity INTEGER NOT NULL DEFAULT 0 CHECK (external_activity = 0),
                    action_authorized INTEGER NOT NULL DEFAULT 0 CHECK (action_authorized = 0),
                    purchase_authorized INTEGER NOT NULL DEFAULT 0 CHECK (purchase_authorized = 0),
                    actions_queued INTEGER NOT NULL DEFAULT 0 CHECK (actions_queued = 0),
                    actions_executed INTEGER NOT NULL DEFAULT 0 CHECK (actions_executed = 0),
                    capability_change TEXT NOT NULL DEFAULT 'none'
                    CHECK (capability_change = 'none'),
                    UNIQUE (source_id, external_item_id),
                    CHECK (
                        (shipping_known = 0 AND shipping_cents IS NULL)
                        OR (shipping_known = 1 AND shipping_cents IS NOT NULL)
                    )
                );
                CREATE TABLE IF NOT EXISTS prayer_requests (
                    prayer_id INTEGER PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_reviewed_at TEXT NOT NULL,
                    entry_method TEXT NOT NULL DEFAULT 'manual'
                    CHECK (entry_method = 'manual'),
                    source_context TEXT NOT NULL
                    CHECK (source_context IN (
                        'direct_to_dustin','slack_prayer_team',
                        'google_messages_giant_killers','whatsapp_sunday','other_private'
                    )),
                    source_reference TEXT NOT NULL DEFAULT '',
                    received_at TEXT NOT NULL,
                    requester_display TEXT NOT NULL DEFAULT '',
                    identity_handling TEXT NOT NULL
                    CHECK (identity_handling IN (
                        'omitted','initials','first_name','full_name_explicit'
                    )),
                    request_text TEXT NOT NULL,
                    fingerprint_sha256 TEXT NOT NULL CHECK (length(fingerprint_sha256) = 64),
                    sharing_scope TEXT NOT NULL
                    CHECK (sharing_scope IN (
                        'private_dustin','source_group_only','explicitly_shareable'
                    )),
                    consent_notes TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active','follow_up','answered','archived')),
                    follow_up_at TEXT,
                    private_notes TEXT NOT NULL DEFAULT '',
                    sensitivity TEXT NOT NULL DEFAULT 'sensitive'
                    CHECK (sensitivity IN ('standard','sensitive','highly_sensitive')),
                    provenance_status TEXT NOT NULL DEFAULT 'user_supplied'
                    CHECK (provenance_status IN (
                        'user_supplied','direct_copy_unverified','clarified_by_dustin'
                    )),
                    confidence TEXT NOT NULL DEFAULT 'high'
                    CHECK (confidence IN ('low','medium','high')),
                    redacted INTEGER NOT NULL DEFAULT 0 CHECK (redacted IN (0,1)),
                    external_content_untrusted INTEGER NOT NULL DEFAULT 1
                    CHECK (external_content_untrusted = 1),
                    cloud_processing_authorized INTEGER NOT NULL DEFAULT 0
                    CHECK (cloud_processing_authorized = 0),
                    cross_post_authorized INTEGER NOT NULL DEFAULT 0
                    CHECK (cross_post_authorized = 0),
                    messages_sent INTEGER NOT NULL DEFAULT 0 CHECK (messages_sent = 0),
                    action_authorized INTEGER NOT NULL DEFAULT 0 CHECK (action_authorized = 0),
                    capability_change TEXT NOT NULL DEFAULT 'none'
                    CHECK (capability_change = 'none'),
                    CHECK (
                        redacted = 0 OR (
                            request_text = '[redacted]' AND requester_display = ''
                            AND source_reference = '' AND consent_notes = ''
                            AND private_notes = '' AND status = 'archived'
                        )
                    )
                );
                CREATE TABLE IF NOT EXISTS prayer_request_changes (
                    change_id INTEGER PRIMARY KEY,
                    prayer_id INTEGER NOT NULL,
                    changed_at TEXT NOT NULL,
                    change_type TEXT NOT NULL
                    CHECK (change_type IN ('created','corrected','status_changed','redacted')),
                    reason TEXT NOT NULL,
                    previous_digest TEXT,
                    new_digest TEXT,
                    status_before TEXT,
                    status_after TEXT NOT NULL,
                    plaintext_history_stored INTEGER NOT NULL DEFAULT 0
                    CHECK (plaintext_history_stored = 0),
                    external_activity INTEGER NOT NULL DEFAULT 0 CHECK (external_activity = 0),
                    messages_sent INTEGER NOT NULL DEFAULT 0 CHECK (messages_sent = 0),
                    capability_change TEXT NOT NULL DEFAULT 'none'
                    CHECK (capability_change = 'none'),
                    FOREIGN KEY(prayer_id) REFERENCES prayer_requests(prayer_id)
                );
                CREATE TABLE IF NOT EXISTS prayer_request_links (
                    link_id INTEGER PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    from_prayer_id INTEGER NOT NULL,
                    to_prayer_id INTEGER NOT NULL,
                    relation_type TEXT NOT NULL
                    CHECK (relation_type IN ('possible_duplicate','related','supersedes')),
                    reason TEXT NOT NULL,
                    confirmed_by TEXT NOT NULL CHECK (confirmed_by = 'dustin'),
                    external_activity INTEGER NOT NULL DEFAULT 0 CHECK (external_activity = 0),
                    capability_change TEXT NOT NULL DEFAULT 'none'
                    CHECK (capability_change = 'none'),
                    CHECK (from_prayer_id != to_prayer_id),
                    UNIQUE (from_prayer_id,to_prayer_id,relation_type),
                    FOREIGN KEY(from_prayer_id) REFERENCES prayer_requests(prayer_id),
                    FOREIGN KEY(to_prayer_id) REFERENCES prayer_requests(prayer_id)
                );
                CREATE TABLE IF NOT EXISTS hardware_targets (
                    id INTEGER PRIMARY KEY, created_at TEXT NOT NULL,
                    component TEXT NOT NULL,
                    target_price_cents INTEGER NOT NULL
                    CHECK (target_price_cents >= 0),
                    expected_capability TEXT NOT NULL,
                    compatibility_status TEXT NOT NULL
                    CHECK (compatibility_status IN ('unknown','needs_review','compatible','incompatible')),
                    notes TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'tracking'
                    CHECK (status IN ('tracking','rejected','acquired')),
                    purchase_authorized INTEGER NOT NULL DEFAULT 0
                    CHECK (purchase_authorized = 0)
                );
                CREATE TABLE IF NOT EXISTS model_handoffs (
                    id INTEGER PRIMARY KEY, created_at TEXT NOT NULL,
                    target TEXT NOT NULL CHECK (target IN ('sophie','bernie')),
                    request TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft','answered','cancelled')),
                    response TEXT,
                    answered_at TEXT,
                    api_budget_cents INTEGER NOT NULL DEFAULT 0
                    CHECK (api_budget_cents = 0),
                    manual_relay_required INTEGER NOT NULL DEFAULT 1
                    CHECK (manual_relay_required = 1),
                    external_activity INTEGER NOT NULL DEFAULT 0
                    CHECK (external_activity = 0),
                    response_untrusted INTEGER NOT NULL DEFAULT 1
                    CHECK (response_untrusted = 1)
                );
                CREATE TABLE IF NOT EXISTS subscription_consultations (
                    id INTEGER PRIMARY KEY, created_at TEXT NOT NULL,
                    request_id TEXT NOT NULL UNIQUE,
                    provider TEXT NOT NULL
                    CHECK (provider IN ('codex_cli','gemini_cli')),
                    user_query TEXT NOT NULL,
                    rendered_prompt TEXT,
                    invocation_attempted INTEGER NOT NULL
                    CHECK (invocation_attempted IN (0,1)),
                    status TEXT NOT NULL
                    CHECK (status IN ('ok','unavailable')),
                    response TEXT NOT NULL,
                    error TEXT
                );
                CREATE TABLE IF NOT EXISTS maintenance_jobs (
                    id INTEGER PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    request_id TEXT NOT NULL UNIQUE,
                    user_request TEXT NOT NULL,
                    operation TEXT NOT NULL
                    CHECK (operation IN ('replace_text','restart_service')),
                    target_path TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'requested'
                    CHECK (status IN (
                        'requested','in_progress','completed','rolled_back',
                        'blocked','approval_required'
                    )),
                    base_branch TEXT,
                    maintenance_branch TEXT,
                    base_commit TEXT,
                    files_read_json TEXT NOT NULL DEFAULT '[]',
                    files_changed_json TEXT NOT NULL DEFAULT '[]',
                    commands_json TEXT NOT NULL DEFAULT '[]',
                    diff_summary TEXT,
                    tests_json TEXT NOT NULL DEFAULT '{}',
                    consultants_json TEXT NOT NULL DEFAULT '[]',
                    final_commit TEXT,
                    rollback_result TEXT,
                    approval_required INTEGER NOT NULL DEFAULT 0
                    CHECK (approval_required IN (0,1)),
                    error TEXT
                );
                CREATE TABLE IF NOT EXISTS maintenance_events (
                    id INTEGER PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    job_id INTEGER NOT NULL,
                    event TEXT NOT NULL,
                    detail_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY(job_id) REFERENCES maintenance_jobs(id)
                );
                CREATE TABLE IF NOT EXISTS learning_units (
                    learning_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    curriculum_version TEXT NOT NULL,
                    unit_digest TEXT NOT NULL,
                    track TEXT NOT NULL,
                    title TEXT NOT NULL,
                    objective TEXT NOT NULL,
                    status TEXT NOT NULL
                    CHECK (status IN ('prepared','complete','attention_required')),
                    authority TEXT NOT NULL,
                    budgets_json TEXT NOT NULL,
                    sources_json TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    claims_json TEXT NOT NULL,
                    contradictions_json TEXT NOT NULL,
                    corrections_json TEXT NOT NULL,
                    assessment_json TEXT NOT NULL,
                    capability_change TEXT NOT NULL DEFAULT 'none'
                    CHECK (capability_change = 'none')
                );
                CREATE TABLE IF NOT EXISTS learning_unit_versions (
                    version_id INTEGER PRIMARY KEY,
                    learning_id TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    curriculum_version TEXT NOT NULL,
                    unit_digest TEXT NOT NULL,
                    status TEXT NOT NULL,
                    record_json TEXT NOT NULL,
                    UNIQUE (learning_id, unit_digest),
                    FOREIGN KEY(learning_id) REFERENCES learning_units(learning_id)
                );
                CREATE TABLE IF NOT EXISTS learning_model_assessments (
                    assessment_id INTEGER PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    curriculum_version TEXT NOT NULL,
                    curriculum_sha256 TEXT NOT NULL,
                    protocol_version TEXT NOT NULL DEFAULT 'labels_only_v0',
                    model TEXT NOT NULL,
                    request_digest TEXT NOT NULL,
                    status TEXT NOT NULL
                    CHECK (status IN ('passed','needs_review','error')),
                    score INTEGER NOT NULL CHECK (score >= 0),
                    total INTEGER NOT NULL CHECK (total > 0 AND score <= total),
                    answers_json TEXT NOT NULL,
                    error_text TEXT,
                    output_untrusted INTEGER NOT NULL DEFAULT 1
                    CHECK (output_untrusted = 1),
                    external_activity INTEGER NOT NULL DEFAULT 0
                    CHECK (external_activity = 0),
                    api_spending_cents INTEGER NOT NULL DEFAULT 0
                    CHECK (api_spending_cents = 0),
                    local_model_requests INTEGER NOT NULL
                    CHECK (local_model_requests IN (0,1)),
                    capability_change TEXT NOT NULL DEFAULT 'none'
                    CHECK (capability_change = 'none')
                );
                CREATE TABLE IF NOT EXISTS history_import_runs (
                    run_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    completed_at TEXT,
                    source_platform TEXT NOT NULL,
                    source_set_id TEXT NOT NULL,
                    source_manifest_sha256 TEXT NOT NULL
                    CHECK (length(source_manifest_sha256) = 64),
                    mode TEXT NOT NULL
                    CHECK (mode IN ('isolated_test_fixture','production')),
                    status TEXT NOT NULL
                    CHECK (status IN ('running','completed','rolled_back')),
                    stats_json TEXT NOT NULL DEFAULT '{}',
                    canonical_records_changed INTEGER NOT NULL DEFAULT 0
                    CHECK (canonical_records_changed = 0),
                    production_import INTEGER NOT NULL DEFAULT 0
                    CHECK (production_import IN (0,1)),
                    error TEXT
                );
                CREATE TABLE IF NOT EXISTS history_sources (
                    source_id INTEGER PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    source_archive TEXT NOT NULL,
                    source_archive_sha256 TEXT NOT NULL
                    CHECK (length(source_archive_sha256) = 64),
                    source_path TEXT NOT NULL,
                    source_member_sha256 TEXT NOT NULL
                    CHECK (length(source_member_sha256) = 64),
                    source_format TEXT NOT NULL,
                    source_bytes INTEGER NOT NULL CHECK (source_bytes >= 0),
                    UNIQUE (run_id,source_archive,source_path,source_member_sha256),
                    FOREIGN KEY(run_id) REFERENCES history_import_runs(run_id)
                );
                CREATE TABLE IF NOT EXISTS history_conversations (
                    conversation_id INTEGER PRIMARY KEY,
                    stable_id TEXT NOT NULL UNIQUE,
                    source_platform TEXT NOT NULL,
                    source_conversation_id TEXT NOT NULL,
                    conversation_title TEXT,
                    source_identity TEXT NOT NULL,
                    first_message_at TEXT NOT NULL,
                    last_message_at TEXT NOT NULL,
                    created_import_run TEXT NOT NULL,
                    historical_only INTEGER NOT NULL DEFAULT 1
                    CHECK (historical_only = 1),
                    canonical_effect INTEGER NOT NULL DEFAULT 0
                    CHECK (canonical_effect = 0),
                    UNIQUE (source_platform,source_conversation_id),
                    FOREIGN KEY(created_import_run) REFERENCES history_import_runs(run_id)
                );
                CREATE TABLE IF NOT EXISTS history_messages (
                    message_id INTEGER PRIMARY KEY,
                    stable_id TEXT NOT NULL UNIQUE,
                    dedupe_key TEXT NOT NULL UNIQUE,
                    conversation_id INTEGER,
                    source_platform TEXT NOT NULL,
                    source_conversation_id TEXT,
                    conversation_title TEXT,
                    source_message_id TEXT,
                    timestamp TEXT NOT NULL,
                    source_timestamp TEXT NOT NULL,
                    speaker TEXT NOT NULL,
                    role TEXT NOT NULL
                    CHECK (role IN ('user','assistant','system','tool','activity')),
                    raw_text TEXT NOT NULL,
                    raw_checksum TEXT NOT NULL CHECK (length(raw_checksum) = 64),
                    source_record_checksum TEXT NOT NULL
                    CHECK (length(source_record_checksum) = 64),
                    source_order INTEGER NOT NULL CHECK (source_order >= 0),
                    message_order INTEGER NOT NULL CHECK (message_order >= 0),
                    source_archive TEXT NOT NULL,
                    source_archive_sha256 TEXT NOT NULL
                    CHECK (length(source_archive_sha256) = 64),
                    source_path TEXT NOT NULL,
                    source_member_sha256 TEXT NOT NULL
                    CHECK (length(source_member_sha256) = 64),
                    source_pointer TEXT NOT NULL,
                    activity_type TEXT NOT NULL,
                    created_import_run TEXT NOT NULL,
                    historical_only INTEGER NOT NULL DEFAULT 1
                    CHECK (historical_only = 1),
                    canonical_effect INTEGER NOT NULL DEFAULT 0
                    CHECK (canonical_effect = 0),
                    FOREIGN KEY(conversation_id)
                    REFERENCES history_conversations(conversation_id),
                    FOREIGN KEY(created_import_run)
                    REFERENCES history_import_runs(run_id)
                );
                CREATE TABLE IF NOT EXISTS history_message_imports (
                    run_id TEXT NOT NULL,
                    message_id INTEGER NOT NULL,
                    source_pointer TEXT NOT NULL,
                    PRIMARY KEY (run_id,message_id),
                    FOREIGN KEY(run_id) REFERENCES history_import_runs(run_id),
                    FOREIGN KEY(message_id) REFERENCES history_messages(message_id)
                );
                CREATE TABLE IF NOT EXISTS history_attachments (
                    attachment_id INTEGER PRIMARY KEY,
                    stable_id TEXT NOT NULL UNIQUE,
                    source_archive TEXT NOT NULL,
                    source_archive_sha256 TEXT NOT NULL
                    CHECK (length(source_archive_sha256) = 64),
                    source_path TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    file_extension TEXT NOT NULL,
                    mime_type TEXT NOT NULL,
                    byte_size INTEGER NOT NULL CHECK (byte_size >= 0),
                    compressed_bytes INTEGER NOT NULL CHECK (compressed_bytes >= 0),
                    checksum_algorithm TEXT NOT NULL CHECK (checksum_algorithm='zip_crc32'),
                    checksum_value TEXT NOT NULL CHECK (length(checksum_value) = 8),
                    directly_referenced INTEGER NOT NULL CHECK (directly_referenced IN (0,1)),
                    payload_inspected INTEGER NOT NULL DEFAULT 0 CHECK (payload_inspected = 0),
                    payload_extracted INTEGER NOT NULL DEFAULT 0 CHECK (payload_extracted = 0),
                    nested_archive_inspected INTEGER NOT NULL DEFAULT 0
                    CHECK (nested_archive_inspected = 0),
                    created_import_run TEXT NOT NULL,
                    historical_only INTEGER NOT NULL DEFAULT 1 CHECK (historical_only = 1),
                    canonical_effect INTEGER NOT NULL DEFAULT 0 CHECK (canonical_effect = 0),
                    UNIQUE (source_archive,source_path),
                    FOREIGN KEY(created_import_run) REFERENCES history_import_runs(run_id)
                );
                CREATE TABLE IF NOT EXISTS history_message_attachments (
                    message_id INTEGER NOT NULL,
                    source_reference TEXT NOT NULL,
                    attachment_id INTEGER,
                    relationship TEXT NOT NULL DEFAULT 'activity_card_reference'
                    CHECK (relationship='activity_card_reference'),
                    PRIMARY KEY (message_id,source_reference),
                    FOREIGN KEY(message_id) REFERENCES history_messages(message_id),
                    FOREIGN KEY(attachment_id) REFERENCES history_attachments(attachment_id)
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS history_messages_fts USING fts5(
                    raw_text,
                    conversation_title,
                    source_platform UNINDEXED,
                    speaker UNINDEXED,
                    timestamp UNINDEXED,
                    content='history_messages',
                    content_rowid='message_id'
                );
                CREATE TRIGGER IF NOT EXISTS history_messages_fts_insert
                AFTER INSERT ON history_messages BEGIN
                    INSERT INTO history_messages_fts(
                        rowid,raw_text,conversation_title,source_platform,speaker,timestamp
                    ) VALUES (
                        new.message_id,new.raw_text,new.conversation_title,
                        new.source_platform,new.speaker,new.timestamp
                    );
                END;
                CREATE TRIGGER IF NOT EXISTS history_messages_fts_delete
                AFTER DELETE ON history_messages BEGIN
                    INSERT INTO history_messages_fts(
                        history_messages_fts,rowid,raw_text,conversation_title,
                        source_platform,speaker,timestamp
                    ) VALUES (
                        'delete',old.message_id,old.raw_text,old.conversation_title,
                        old.source_platform,old.speaker,old.timestamp
                    );
                END;
                CREATE TRIGGER IF NOT EXISTS history_messages_fts_update
                AFTER UPDATE ON history_messages BEGIN
                    INSERT INTO history_messages_fts(
                        history_messages_fts,rowid,raw_text,conversation_title,
                        source_platform,speaker,timestamp
                    ) VALUES (
                        'delete',old.message_id,old.raw_text,old.conversation_title,
                        old.source_platform,old.speaker,old.timestamp
                    );
                    INSERT INTO history_messages_fts(
                        rowid,raw_text,conversation_title,source_platform,speaker,timestamp
                    ) VALUES (
                        new.message_id,new.raw_text,new.conversation_title,
                        new.source_platform,new.speaker,new.timestamp
                    );
                END;
                CREATE TABLE IF NOT EXISTS retrieval_events (
                    request_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    query_sha256 TEXT NOT NULL CHECK (length(query_sha256) = 64),
                    trigger_reason TEXT NOT NULL,
                    question_domain TEXT NOT NULL,
                    query_terms_json TEXT NOT NULL,
                    entity_candidates_json TEXT NOT NULL,
                    source_types_json TEXT NOT NULL,
                    evidence_ids_json TEXT NOT NULL,
                    knowledge_state TEXT NOT NULL CHECK (
                        knowledge_state IN (
                            'VERIFIED','CANONICAL','RETRIEVED',
                            'INFERRED','UNKNOWN','CONFLICT'
                        )
                    ),
                    exclusions_json TEXT NOT NULL DEFAULT '[]',
                    packet_chars INTEGER NOT NULL CHECK (packet_chars >= 0),
                    failure_classification TEXT,
                    delivery_status TEXT NOT NULL DEFAULT 'built' CHECK (
                        delivery_status IN ('built','injected','unavailable')
                    ),
                    packet_sha256 TEXT CHECK (
                        packet_sha256 IS NULL OR length(packet_sha256) = 64
                    )
                );
                CREATE TABLE IF NOT EXISTS entities (
                    entity_id TEXT PRIMARY KEY,
                    canonical_name TEXT NOT NULL,
                    normalized_name TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'active' CHECK (
                        status IN ('active','inactive','merged')
                    ),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS entities_normalized_name_idx
                    ON entities(normalized_name);
                CREATE TABLE IF NOT EXISTS entity_aliases (
                    alias_id TEXT PRIMARY KEY,
                    entity_id TEXT NOT NULL,
                    alias_text TEXT NOT NULL,
                    normalized_alias TEXT NOT NULL,
                    alias_type TEXT NOT NULL CHECK (
                        alias_type IN (
                            'nickname','acronym','former_name','speech_variant','shorthand'
                        )
                    ),
                    evidence_class TEXT NOT NULL CHECK (
                        evidence_class IN (
                            'VERIFIED','CANONICAL','RETRIEVED','INFERRED','UNKNOWN'
                        )
                    ),
                    confidence REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
                    source_pointer TEXT NOT NULL,
                    valid_from TEXT,
                    valid_to TEXT,
                    context_entity_id TEXT,
                    ambiguity_state TEXT NOT NULL DEFAULT 'unambiguous' CHECK (
                        ambiguity_state IN ('unambiguous','context_required','ambiguous')
                    ),
                    status TEXT NOT NULL DEFAULT 'active' CHECK (
                        status IN ('active','superseded','rejected')
                    ),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(entity_id,normalized_alias),
                    FOREIGN KEY(entity_id) REFERENCES entities(entity_id)
                );
                CREATE INDEX IF NOT EXISTS entity_aliases_normalized_idx
                    ON entity_aliases(normalized_alias,status);
                CREATE TABLE IF NOT EXISTS entity_relationships (
                    relationship_id TEXT PRIMARY KEY,
                    subject_entity_id TEXT NOT NULL,
                    predicate TEXT NOT NULL,
                    object_entity_id TEXT,
                    object_literal TEXT,
                    evidence_class TEXT NOT NULL,
                    confidence REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
                    source_pointer TEXT NOT NULL,
                    valid_from TEXT,
                    valid_to TEXT,
                    status TEXT NOT NULL DEFAULT 'active' CHECK (
                        status IN ('candidate','active','disputed','superseded','rejected')
                    ),
                    superseded_by_relationship_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    CHECK ((object_entity_id IS NULL) != (object_literal IS NULL)),
                    FOREIGN KEY(subject_entity_id) REFERENCES entities(entity_id),
                    FOREIGN KEY(object_entity_id) REFERENCES entities(entity_id)
                );
                CREATE TABLE IF NOT EXISTS memory_claims (
                    claim_id TEXT PRIMARY KEY,
                    subject_entity_id TEXT NOT NULL,
                    predicate TEXT NOT NULL,
                    object_entity_id TEXT,
                    value_text TEXT,
                    memory_layer TEXT NOT NULL CHECK (
                        memory_layer IN ('identity','semantic','episodic','procedural','relational')
                    ),
                    status TEXT NOT NULL CHECK (
                        status IN ('candidate','active','disputed','superseded','rejected')
                    ),
                    evidence_class TEXT NOT NULL CHECK (
                        evidence_class IN (
                            'VERIFIED','CANONICAL','RETRIEVED','INFERRED','UNKNOWN'
                        )
                    ),
                    authority_scope TEXT NOT NULL,
                    confidence REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
                    confidence_basis TEXT NOT NULL,
                    valid_from TEXT,
                    valid_to TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    approved_by TEXT,
                    reviewed_at TEXT,
                    canonical_effect INTEGER NOT NULL DEFAULT 0 CHECK (
                        canonical_effect IN (0,1)
                    ),
                    superseded_by_claim_id TEXT,
                    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
                    CHECK ((object_entity_id IS NULL) != (value_text IS NULL)),
                    CHECK (
                        canonical_effect = 0 OR (
                            status = 'active' AND evidence_class = 'CANONICAL'
                            AND approved_by IS NOT NULL AND reviewed_at IS NOT NULL
                        )
                    ),
                    FOREIGN KEY(subject_entity_id) REFERENCES entities(entity_id),
                    FOREIGN KEY(object_entity_id) REFERENCES entities(entity_id)
                );
                CREATE INDEX IF NOT EXISTS memory_claims_subject_predicate_idx
                    ON memory_claims(subject_entity_id,predicate,status,canonical_effect);
                CREATE TABLE IF NOT EXISTS claim_evidence (
                    claim_id TEXT NOT NULL,
                    evidence_id TEXT NOT NULL,
                    relation_type TEXT NOT NULL CHECK (
                        relation_type IN (
                            'supports','contradicts','derived_from','execution_receipt',
                            'supersedes','refines','caused_by','related_to'
                        )
                    ),
                    source_type TEXT NOT NULL,
                    source_platform TEXT,
                    conversation_id TEXT,
                    history_message_id INTEGER,
                    source_message_id TEXT,
                    source_timestamp TEXT,
                    role TEXT,
                    speaker TEXT,
                    attribution TEXT NOT NULL DEFAULT 'ambiguous_source' CHECK (
                        attribution IN (
                            'direct_user_assertion','assistant_assertion',
                            'quoted_or_pasted_content','ambiguous_source'
                        )
                    ),
                    source_pointer TEXT NOT NULL,
                    evidence_class TEXT NOT NULL,
                    excerpt_sha256 TEXT,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(claim_id,evidence_id,relation_type),
                    FOREIGN KEY(claim_id) REFERENCES memory_claims(claim_id),
                    FOREIGN KEY(history_message_id) REFERENCES history_messages(message_id)
                );
                CREATE TABLE IF NOT EXISTS claim_conflicts (
                    conflict_id TEXT PRIMARY KEY,
                    claim_scope TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('unresolved','resolved')),
                    resolver TEXT,
                    resolution_timestamp TEXT,
                    resolution_reason TEXT,
                    resolution_claim_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    CHECK (
                        status = 'unresolved' OR (
                            resolver IS NOT NULL AND resolution_timestamp IS NOT NULL
                            AND resolution_reason IS NOT NULL
                            AND resolution_claim_id IS NOT NULL
                        )
                    )
                );
                CREATE TABLE IF NOT EXISTS conflict_claims (
                    conflict_id TEXT NOT NULL,
                    claim_id TEXT NOT NULL,
                    outcome TEXT NOT NULL CHECK (
                        outcome IN ('competing','prevailing','superseded','rejected','context')
                    ),
                    PRIMARY KEY(conflict_id,claim_id),
                    FOREIGN KEY(conflict_id) REFERENCES claim_conflicts(conflict_id),
                    FOREIGN KEY(claim_id) REFERENCES memory_claims(claim_id)
                );
                CREATE TABLE IF NOT EXISTS canonical_adjudications (
                    adjudication_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    authorized_by TEXT NOT NULL,
                    authority_scope TEXT NOT NULL,
                    explicit_statement TEXT NOT NULL,
                    statement_sha256 TEXT NOT NULL CHECK (length(statement_sha256)=64),
                    source_pointer TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256)=64),
                    conflict_id TEXT,
                    status TEXT NOT NULL CHECK (status IN ('applied','rejected')),
                    actions_executed INTEGER NOT NULL DEFAULT 0 CHECK (actions_executed=0)
                );
                CREATE TABLE IF NOT EXISTS candidate_extractions (
                    extraction_id TEXT PRIMARY KEY,
                    claim_id TEXT NOT NULL,
                    extractor_id TEXT NOT NULL,
                    extractor_version TEXT,
                    extracted_at TEXT NOT NULL,
                    claim_category TEXT NOT NULL,
                    temporal_hint TEXT,
                    notes TEXT,
                    raw_proposal_json TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(claim_id) REFERENCES memory_claims(claim_id)
                );
                """
            )
            memory_columns = {
                str(row[1]) for row in connection.execute("PRAGMA table_info(memories)").fetchall()
            }
            if "status" not in memory_columns:
                connection.execute("ALTER TABLE memories ADD COLUMN status TEXT NOT NULL DEFAULT 'active'")
            if "updated_at" not in memory_columns:
                connection.execute("ALTER TABLE memories ADD COLUMN updated_at TEXT")
            for table in ("model_proposals", "external_proposals"):
                proposal_columns = {
                    str(row[1])
                    for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
                }
                if "decided_at" not in proposal_columns:
                    connection.execute(f"ALTER TABLE {table} ADD COLUMN decided_at TEXT")
                if "decision_reason" not in proposal_columns:
                    connection.execute(f"ALTER TABLE {table} ADD COLUMN decision_reason TEXT")
            assessment_columns = {
                str(row[1])
                for row in connection.execute(
                    "PRAGMA table_info(learning_model_assessments)"
                ).fetchall()
            }
            if "protocol_version" not in assessment_columns:
                connection.execute(
                    "ALTER TABLE learning_model_assessments ADD COLUMN protocol_version "
                    "TEXT NOT NULL DEFAULT 'labels_only_v0'"
                )
            attachment_link_columns = {
                str(row[1])
                for row in connection.execute(
                    "PRAGMA table_info(history_message_attachments)"
                ).fetchall()
            }
            if "attachment_id" not in attachment_link_columns:
                connection.execute(
                    "ALTER TABLE history_message_attachments "
                    "ADD COLUMN attachment_id INTEGER"
                )
            if "relationship" not in attachment_link_columns:
                connection.execute(
                    "ALTER TABLE history_message_attachments ADD COLUMN relationship "
                    "TEXT NOT NULL DEFAULT 'activity_card_reference'"
                )
            retrieval_columns = {
                str(row[1]) for row in connection.execute(
                    "PRAGMA table_info(retrieval_events)"
                ).fetchall()
            }
            retrieval_additions = {
                "resolved_entity_ids_json": "TEXT NOT NULL DEFAULT '[]'",
                "alias_matches_json": "TEXT NOT NULL DEFAULT '[]'",
                "candidate_ambiguity_json": "TEXT NOT NULL DEFAULT '[]'",
                "canonical_claim_ids_json": "TEXT NOT NULL DEFAULT '[]'",
                "conflict_ids_json": "TEXT NOT NULL DEFAULT '[]'",
                "superseded_evidence_json": "TEXT NOT NULL DEFAULT '[]'",
                "adjudication_state": "TEXT NOT NULL DEFAULT 'not_applicable'",
            }
            for column, definition in retrieval_additions.items():
                if column not in retrieval_columns:
                    connection.execute(
                        f"ALTER TABLE retrieval_events ADD COLUMN {column} {definition}"
                    )
            claim_evidence_columns = {
                str(row[1])
                for row in connection.execute(
                    "PRAGMA table_info(claim_evidence)"
                ).fetchall()
            }
            if "attribution" not in claim_evidence_columns:
                connection.execute(
                    "ALTER TABLE claim_evidence ADD COLUMN attribution "
                    "TEXT NOT NULL DEFAULT 'ambiguous_source'"
                )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def add_message(self, speaker: str, content: str) -> None:
        with self._connect() as connection:
            connection.execute("INSERT INTO messages(created_at,speaker,content) VALUES (?,?,?)", (self._now(), speaker, content))

    def recent_messages(self, limit: int = 20) -> list[tuple[str, str]]:
        with self._connect() as connection:
            rows = connection.execute("SELECT speaker,content FROM messages ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [(row["speaker"], row["content"]) for row in reversed(rows)]

    @staticmethod
    def _history_field(message: object, name: str) -> object:
        if isinstance(message, dict):
            if name not in message:
                raise ValueError(f"Historical message is missing {name}")
            return message[name]
        if not hasattr(message, name):
            raise ValueError(f"Historical message is missing {name}")
        return getattr(message, name)

    def history_import_run(self, run_id: str) -> dict[str, object] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM history_import_runs WHERE run_id=?", (run_id,)
            ).fetchone()
        if row is None:
            return None
        record = dict(row)
        record["stats"] = json.loads(str(record.pop("stats_json")))
        record["canonical_records_changed"] = int(
            record["canonical_records_changed"]
        )
        record["production_import"] = bool(record["production_import"])
        return record

    def history_counts(self) -> dict[str, int]:
        with self._connect() as connection:
            return {
                name: int(
                    connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
                )
                for name in (
                    "history_import_runs",
                    "history_sources",
                    "history_conversations",
                    "history_messages",
                    "history_message_imports",
                    "history_attachments",
                    "history_message_attachments",
                )
            }

    def history_replay_preflight(
        self,
        *,
        messages: Iterator[object] | tuple[object, ...] | list[object],
        attachments: Iterator[object] | tuple[object, ...] | list[object],
    ) -> dict[str, object]:
        """Compare a replay to stored dedupe identities without writing."""

        materialized_messages = tuple(messages)
        materialized_attachments = tuple(attachments)
        message_existing = 0
        message_conflicts = 0
        attachment_existing = 0
        attachment_conflicts = 0
        with self._connect() as connection:
            for message in materialized_messages:
                row = connection.execute(
                    "SELECT raw_checksum FROM history_messages "
                    "WHERE stable_id=? OR dedupe_key=?",
                    (
                        str(self._history_field(message, "stable_id")),
                        str(self._history_field(message, "dedupe_key")),
                    ),
                ).fetchone()
                if row is not None:
                    message_existing += 1
                    if row["raw_checksum"] != str(
                        self._history_field(message, "raw_checksum")
                    ).lower():
                        message_conflicts += 1
            for attachment in materialized_attachments:
                row = connection.execute(
                    "SELECT byte_size,checksum_value FROM history_attachments "
                    "WHERE stable_id=? OR (source_archive=? AND source_path=?)",
                    (
                        str(self._history_field(attachment, "stable_id")),
                        str(self._history_field(attachment, "source_archive")),
                        str(self._history_field(attachment, "source_path")),
                    ),
                ).fetchone()
                if row is not None:
                    attachment_existing += 1
                    if (
                        int(row["byte_size"])
                        != int(self._history_field(attachment, "byte_size"))
                        or row["checksum_value"]
                        != str(
                            self._history_field(attachment, "checksum_value")
                        ).lower()
                    ):
                        attachment_conflicts += 1
        return {
            "messages_requested": len(materialized_messages),
            "messages_existing": message_existing,
            "messages_would_insert": len(materialized_messages) - message_existing,
            "message_conflicts": message_conflicts,
            "attachments_requested": len(materialized_attachments),
            "attachments_existing": attachment_existing,
            "attachments_would_insert": len(materialized_attachments)
            - attachment_existing,
            "attachment_conflicts": attachment_conflicts,
            "writes_performed": 0,
            "canonical_changes": 0,
        }

    def history_attachment_summary(self) -> dict[str, object]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT file_extension,directly_referenced,COUNT(*) record_count,"
                "SUM(byte_size) total_bytes FROM history_attachments "
                "GROUP BY file_extension,directly_referenced "
                "ORDER BY file_extension,directly_referenced"
            ).fetchall()
            linked = int(
                connection.execute(
                    "SELECT COUNT(*) FROM history_message_attachments "
                    "WHERE attachment_id IS NOT NULL"
                ).fetchone()[0]
            )
        return {
            "by_type_and_reference": [dict(row) for row in rows],
            "message_relationships": linked,
            "payloads_inspected": 0,
            "payloads_extracted": 0,
            "historical_only": True,
            "canonical_effect": False,
        }

    def import_history_test_fixture(
        self,
        *,
        run_id: str,
        source_set_id: str,
        source_manifest_sha256: str,
        source_format: str,
        source_bytes: int,
        messages: Iterator[object] | tuple[object, ...] | list[object],
        isolated_test_fixture: bool = False,
        simulate_failure_after: int | None = None,
    ) -> dict[str, object]:
        """Exercise the normalized importer only on explicit test fixtures."""

        if not isolated_test_fixture:
            raise PermissionError(
                "Production history import is locked outside the Phase 2 path"
            )
        return self._import_history_records(
            run_id=run_id,
            source_set_id=source_set_id,
            source_manifest_sha256=source_manifest_sha256,
            source_format=source_format,
            source_bytes=source_bytes,
            messages=messages,
            attachments=(),
            mode="isolated_test_fixture",
            authorized=isolated_test_fixture,
            simulate_failure_after=simulate_failure_after,
        )

    def import_raw_evidence(
        self,
        *,
        run_id: str,
        source_set_id: str,
        source_manifest_sha256: str,
        source_format: str,
        source_bytes: int,
        messages: Iterator[object] | tuple[object, ...] | list[object],
        attachments: Iterator[object] | tuple[object, ...] | list[object] = (),
        mode: str = "isolated_test_fixture",
        authorized: bool = True,
        expected: dict[str, object] | None = None,
        simulate_failure_after: int | None = None,
    ) -> dict[str, object]:
        """Provider-neutral raw evidence ingestion into SQLite history tables.

        Raw evidence records are preserved as historical-only (historical_only=1, canonical_effect=0)
        and never automatically create active memory_claims or affect canonical priming.
        """
        if not authorized:
            raise PermissionError("Raw evidence import authorization required")
        return self._import_history_records(
            run_id=run_id,
            source_set_id=source_set_id,
            source_manifest_sha256=source_manifest_sha256,
            source_format=source_format,
            source_bytes=source_bytes,
            messages=messages,
            attachments=attachments,
            mode=mode,
            authorized=authorized,
            expected=expected,
            simulate_failure_after=simulate_failure_after,
        )

    def import_history_production(
        self,
        *,
        run_id: str,
        source_set_id: str,
        source_manifest_sha256: str,
        source_format: str,
        source_bytes: int,
        messages: Iterator[object] | tuple[object, ...] | list[object],
        attachments: Iterator[object] | tuple[object, ...] | list[object],
        confirmation: str,
        expected: dict[str, object],
    ) -> dict[str, object]:
        """Perform the one approved Gemini Phase 2 transaction or fail closed."""

        if confirmation != "IMPORT_VERIFIED_GEMINI_PHASE2":
            raise PermissionError("Gemini production import requires Phase 2 confirmation")
        prior = self.history_import_run(run_id)
        if prior is None:
            counts = self.history_counts()
            occupied = {
                key: value
                for key, value in counts.items()
                if key != "history_import_runs" and value != 0
            }
            if occupied:
                raise ValueError(
                    f"Production history tables are not empty: {sorted(occupied)}"
                )
            with self._connect() as connection:
                unsafe_prior_runs = int(
                    connection.execute(
                        "SELECT COUNT(*) FROM history_import_runs WHERE "
                        "status!='rolled_back' OR canonical_records_changed!=0"
                    ).fetchone()[0]
                )
            if unsafe_prior_runs:
                raise ValueError(
                    "Production history has a prior non-rollback import run"
                )
        return self._import_history_records(
            run_id=run_id,
            source_set_id=source_set_id,
            source_manifest_sha256=source_manifest_sha256,
            source_format=source_format,
            source_bytes=source_bytes,
            messages=messages,
            attachments=attachments,
            mode="production",
            authorized=True,
            expected=expected,
        )

    def _import_history_records(
        self,
        *,
        run_id: str,
        source_set_id: str,
        source_manifest_sha256: str,
        source_format: str,
        source_bytes: int,
        messages: Iterator[object] | tuple[object, ...] | list[object],
        attachments: Iterator[object] | tuple[object, ...] | list[object],
        mode: str,
        authorized: bool,
        expected: dict[str, object] | None = None,
        simulate_failure_after: int | None = None,
    ) -> dict[str, object]:
        if mode not in {"isolated_test_fixture", "production"} or not authorized:
            raise PermissionError("History import authorization is invalid")
        if (
            not run_id
            or len(run_id) > 120
            or ".." in run_id
            or run_id.startswith(".")
            or run_id.endswith(".")
        ):
            raise ValueError("History import run ID is invalid for its mode")
        run_pattern = (
            r"test[-_][A-Za-z0-9._-]{1,119}"
            if mode == "isolated_test_fixture"
            else r"[A-Za-z0-9][A-Za-z0-9._-]{0,119}"
        )
        if not re.fullmatch(run_pattern, run_id):
            raise ValueError("History import run ID is invalid for its mode")
        if not source_set_id.strip() or len(source_set_id) > 200:
            raise ValueError("History source set ID is invalid")
        manifest_sha256 = source_manifest_sha256.strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", manifest_sha256):
            raise ValueError("History source manifest SHA-256 is invalid")
        if not source_format.strip() or len(source_format) > 200:
            raise ValueError("History source format is invalid")
        if source_bytes < 0:
            raise ValueError("History source byte count is invalid")
        materialized = tuple(messages)
        if not materialized:
            raise ValueError("History fixture must include at least one record")
        attachment_materialized = tuple(attachments)
        if (
            mode == "production"
            and not attachment_materialized
            and (expected is not None and int(expected.get("attachments", 0)) > 0)
        ):
            raise ValueError("Production history import requires attachment metadata")
        if mode == "production" and expected is None:
            raise ValueError("Production history import requires exact expected counts")

        prior = self.history_import_run(run_id)
        if prior is not None and prior["status"] == "completed":
            if (
                prior["source_set_id"] != source_set_id
                or prior["source_manifest_sha256"] != manifest_sha256
            ):
                raise ValueError("Completed history run ID belongs to another source set")
            cached = dict(prior["stats"])
            cached["idempotent_replay"] = True
            return cached

        now = self._now()
        inserted = 0
        deduplicated = 0
        attachments_inserted = 0
        attachments_deduplicated = 0
        conversation_keys: set[tuple[str, str]] = set()
        try:
            with self._connect() as connection:
                connection.execute("PRAGMA foreign_keys=ON")
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "INSERT INTO history_import_runs("
                    "run_id,created_at,source_platform,source_set_id,"
                    "source_manifest_sha256,mode,status,production_import) "
                    "VALUES (?,?,?,?,?,?,'running',?) "
                    "ON CONFLICT(run_id) DO UPDATE SET "
                    "created_at=excluded.created_at,completed_at=NULL,"
                    "source_platform=excluded.source_platform,"
                    "source_set_id=excluded.source_set_id,"
                    "source_manifest_sha256=excluded.source_manifest_sha256,"
                    "mode=excluded.mode,status='running',stats_json='{}',error=NULL "
                    "WHERE history_import_runs.status='rolled_back'",
                    (
                        run_id,
                        now,
                        str(self._history_field(materialized[0], "source_platform")),
                        source_set_id,
                        manifest_sha256,
                        mode,
                        int(mode == "production"),
                    ),
                )

                sources: set[tuple[str, str, str, str]] = set()
                for message in materialized:
                    sources.add(
                        (
                            str(self._history_field(message, "source_archive")),
                            str(
                                self._history_field(
                                    message, "source_archive_sha256"
                                )
                            ).lower(),
                            str(self._history_field(message, "source_path")),
                            str(
                                self._history_field(message, "source_member_sha256")
                            ).lower(),
                        )
                    )
                for archive, archive_sha, source_path, member_sha in sorted(sources):
                    connection.execute(
                        "INSERT OR IGNORE INTO history_sources("
                        "run_id,source_archive,source_archive_sha256,source_path,"
                        "source_member_sha256,source_format,source_bytes) "
                        "VALUES (?,?,?,?,?,?,?)",
                        (
                            run_id,
                            archive,
                            archive_sha,
                            source_path,
                            member_sha,
                            source_format,
                            source_bytes,
                        ),
                    )

                reference_to_attachment: dict[str, int] = {}
                for attachment in attachment_materialized:
                    inspected = bool(
                        self._history_field(attachment, "payload_inspected")
                    )
                    extracted = bool(
                        self._history_field(attachment, "payload_extracted")
                    )
                    nested_inspected = bool(
                        self._history_field(attachment, "nested_archive_inspected")
                    )
                    if inspected or extracted or nested_inspected:
                        raise ValueError("Attachment payload policy was violated")
                    attachment_values = (
                        str(self._history_field(attachment, "stable_id")),
                        str(self._history_field(attachment, "source_archive")),
                        str(
                            self._history_field(
                                attachment, "source_archive_sha256"
                            )
                        ).lower(),
                        str(self._history_field(attachment, "source_path")),
                        str(self._history_field(attachment, "filename")),
                        str(self._history_field(attachment, "file_extension")),
                        str(self._history_field(attachment, "mime_type")),
                        int(self._history_field(attachment, "byte_size")),
                        int(self._history_field(attachment, "compressed_bytes")),
                        str(self._history_field(attachment, "checksum_algorithm")),
                        str(self._history_field(attachment, "checksum_value")).lower(),
                        int(
                            bool(
                                self._history_field(
                                    attachment, "directly_referenced"
                                )
                            )
                        ),
                        0,
                        0,
                        0,
                        run_id,
                        1,
                        0,
                    )
                    cursor = connection.execute(
                        "INSERT OR IGNORE INTO history_attachments("
                        "stable_id,source_archive,source_archive_sha256,source_path,"
                        "filename,file_extension,mime_type,byte_size,compressed_bytes,"
                        "checksum_algorithm,checksum_value,directly_referenced,"
                        "payload_inspected,payload_extracted,nested_archive_inspected,"
                        "created_import_run,historical_only,canonical_effect) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        attachment_values,
                    )
                    if cursor.rowcount == 1:
                        attachments_inserted += 1
                    else:
                        attachments_deduplicated += 1
                    attachment_row = connection.execute(
                        "SELECT attachment_id,byte_size,checksum_value FROM "
                        "history_attachments WHERE stable_id=? OR "
                        "(source_archive=? AND source_path=?)",
                        (
                            attachment_values[0],
                            attachment_values[1],
                            attachment_values[3],
                        ),
                    ).fetchone()
                    if (
                        attachment_row is None
                        or int(attachment_row["byte_size"]) != attachment_values[7]
                        or attachment_row["checksum_value"] != attachment_values[10]
                    ):
                        raise ValueError(
                            "Historical attachment identity conflicts with metadata"
                        )
                    attachment_row_id = int(attachment_row["attachment_id"])
                    source_references = tuple(
                        str(value)
                        for value in self._history_field(
                            attachment, "source_references"
                        )
                    )
                    if bool(attachment_values[11]) != bool(source_references):
                        raise ValueError(
                            "Attachment reference flag conflicts with source evidence"
                        )
                    for reference in source_references:
                        existing_attachment = reference_to_attachment.setdefault(
                            reference, attachment_row_id
                        )
                        if existing_attachment != attachment_row_id:
                            raise ValueError(
                                "Attachment source reference resolves ambiguously"
                            )

                for index, message in enumerate(materialized):
                    platform = str(self._history_field(message, "source_platform"))
                    source_conversation_id_value = self._history_field(
                        message, "source_conversation_id"
                    )
                    source_conversation_id = (
                        None
                        if source_conversation_id_value is None
                        else str(source_conversation_id_value)
                    )
                    title_value = self._history_field(message, "conversation_title")
                    title = None if title_value is None else str(title_value)
                    timestamp = str(self._history_field(message, "timestamp"))
                    role = str(self._history_field(message, "role"))
                    conversation_row_id: int | None = None
                    if source_conversation_id and role in {"user", "assistant"}:
                        conversation_keys.add((platform, source_conversation_id))
                        stable_material = f"{platform}\0{source_conversation_id}"
                        conversation_stable_id = "histconv_" + hashlib.sha256(
                            stable_material.encode("utf-8")
                        ).hexdigest()
                        connection.execute(
                            "INSERT INTO history_conversations("
                            "stable_id,source_platform,source_conversation_id,"
                            "conversation_title,source_identity,first_message_at,"
                            "last_message_at,created_import_run) VALUES (?,?,?,?,?,?,?,?) "
                            "ON CONFLICT(source_platform,source_conversation_id) DO UPDATE SET "
                            "conversation_title=COALESCE("
                            "history_conversations.conversation_title,excluded.conversation_title),"
                            "first_message_at=MIN(history_conversations.first_message_at,"
                            "excluded.first_message_at),"
                            "last_message_at=MAX(history_conversations.last_message_at,"
                            "excluded.last_message_at)",
                            (
                                conversation_stable_id,
                                platform,
                                source_conversation_id,
                                title,
                                "account_owner",
                                timestamp,
                                timestamp,
                                run_id,
                            ),
                        )
                        conversation_row_id = int(
                            connection.execute(
                                "SELECT conversation_id FROM history_conversations "
                                "WHERE source_platform=? AND source_conversation_id=?",
                                (platform, source_conversation_id),
                            ).fetchone()[0]
                        )

                    values = (
                        str(self._history_field(message, "stable_id")),
                        str(self._history_field(message, "dedupe_key")),
                        conversation_row_id,
                        platform,
                        source_conversation_id,
                        title,
                        self._history_field(message, "source_message_id"),
                        timestamp,
                        str(self._history_field(message, "source_timestamp")),
                        str(self._history_field(message, "speaker")),
                        role,
                        str(self._history_field(message, "raw_text")),
                        str(self._history_field(message, "raw_checksum")).lower(),
                        str(
                            self._history_field(message, "source_record_checksum")
                        ).lower(),
                        int(self._history_field(message, "source_order")),
                        int(self._history_field(message, "message_order")),
                        str(self._history_field(message, "source_archive")),
                        str(
                            self._history_field(message, "source_archive_sha256")
                        ).lower(),
                        str(self._history_field(message, "source_path")),
                        str(
                            self._history_field(message, "source_member_sha256")
                        ).lower(),
                        str(self._history_field(message, "source_pointer")),
                        str(self._history_field(message, "activity_type")),
                        run_id,
                    )
                    cursor = connection.execute(
                        "INSERT OR IGNORE INTO history_messages("
                        "stable_id,dedupe_key,conversation_id,source_platform,"
                        "source_conversation_id,conversation_title,source_message_id,"
                        "timestamp,source_timestamp,speaker,role,raw_text,raw_checksum,"
                        "source_record_checksum,source_order,message_order,source_archive,"
                        "source_archive_sha256,source_path,source_member_sha256,"
                        "source_pointer,activity_type,created_import_run) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        values,
                    )
                    if cursor.rowcount == 1:
                        inserted += 1
                    else:
                        deduplicated += 1
                    message_row = connection.execute(
                        "SELECT message_id,raw_checksum FROM history_messages "
                        "WHERE stable_id=? OR dedupe_key=?",
                        (values[0], values[1]),
                    ).fetchone()
                    if message_row is None or message_row["raw_checksum"] != values[12]:
                        raise ValueError("Historical dedupe identity conflicts with content")
                    message_row_id = int(message_row["message_id"])
                    connection.execute(
                        "INSERT OR IGNORE INTO history_message_imports("
                        "run_id,message_id,source_pointer) VALUES (?,?,?)",
                        (run_id, message_row_id, values[20]),
                    )
                    references = self._history_field(
                        message, "attachment_references"
                    )
                    for reference in sorted({str(item) for item in references}):
                        attachment_id = reference_to_attachment.get(reference)
                        if mode == "production" and attachment_id is None:
                            raise ValueError(
                                "Message attachment reference lacks metadata"
                            )
                        connection.execute(
                            "INSERT OR IGNORE INTO history_message_attachments("
                            "message_id,source_reference,attachment_id,relationship) "
                            "VALUES (?,?,?,'activity_card_reference')",
                            (message_row_id, reference, attachment_id),
                        )
                    if (
                        simulate_failure_after is not None
                        and index + 1 >= simulate_failure_after
                    ):
                        raise RuntimeError("Simulated isolated history import failure")

                role_counts = {
                    str(row["role"]): int(row["record_count"])
                    for row in connection.execute(
                        "SELECT role,COUNT(*) record_count FROM history_messages "
                        "GROUP BY role"
                    ).fetchall()
                }
                date_row = connection.execute(
                    "SELECT MIN(timestamp) first_timestamp,MAX(timestamp) last_timestamp "
                    "FROM history_messages"
                ).fetchone()
                unreferenced_types = {
                    str(row["file_extension"]): int(row["record_count"])
                    for row in connection.execute(
                        "SELECT file_extension,COUNT(*) record_count "
                        "FROM history_attachments WHERE directly_referenced=0 "
                        "GROUP BY file_extension"
                    ).fetchall()
                }
                actual: dict[str, object] = {
                    "messages": int(
                        connection.execute(
                            "SELECT COUNT(*) FROM history_messages"
                        ).fetchone()[0]
                    ),
                    "conversations": int(
                        connection.execute(
                            "SELECT COUNT(*) FROM history_conversations"
                        ).fetchone()[0]
                    ),
                    "user_messages": role_counts.get("user", 0),
                    "assistant_messages": role_counts.get("assistant", 0),
                    "activity_messages": role_counts.get("activity", 0),
                    "attachments": int(
                        connection.execute(
                            "SELECT COUNT(*) FROM history_attachments"
                        ).fetchone()[0]
                    ),
                    "direct_attachments": int(
                        connection.execute(
                            "SELECT COUNT(*) FROM history_attachments "
                            "WHERE directly_referenced=1"
                        ).fetchone()[0]
                    ),
                    "unreferenced_attachments": int(
                        connection.execute(
                            "SELECT COUNT(*) FROM history_attachments "
                            "WHERE directly_referenced=0"
                        ).fetchone()[0]
                    ),
                    "attachment_links": int(
                        connection.execute(
                            "SELECT COUNT(*) FROM history_message_attachments"
                        ).fetchone()[0]
                    ),
                    "fts_messages": int(
                        connection.execute(
                            "SELECT COUNT(*) FROM history_messages_fts"
                        ).fetchone()[0]
                    ),
                    "first_timestamp": date_row["first_timestamp"],
                    "last_timestamp": date_row["last_timestamp"],
                    "unreferenced_types": unreferenced_types,
                    "payloads_inspected": int(
                        connection.execute(
                            "SELECT COUNT(*) FROM history_attachments "
                            "WHERE payload_inspected!=0 OR payload_extracted!=0 "
                            "OR nested_archive_inspected!=0"
                        ).fetchone()[0]
                    ),
                    "canonical_effect_rows": int(
                        connection.execute(
                            "SELECT (SELECT COUNT(*) FROM history_messages "
                            "WHERE canonical_effect!=0)+(SELECT COUNT(*) "
                            "FROM history_conversations WHERE canonical_effect!=0)+"
                            "(SELECT COUNT(*) FROM history_attachments "
                            "WHERE canonical_effect!=0)"
                        ).fetchone()[0]
                    ),
                }
                if expected is not None:
                    unknown = set(expected) - set(actual)
                    if unknown:
                        raise ValueError(
                            f"Unknown production history expectations: {sorted(unknown)}"
                        )
                    mismatches = {
                        key: {"expected": value, "actual": actual[key]}
                        for key, value in expected.items()
                        if actual[key] != value
                    }
                    if mismatches:
                        raise ValueError(
                            "Production history verification failed: "
                            + json.dumps(mismatches, sort_keys=True)
                        )

                stats: dict[str, object] = {
                    "requested_messages": len(materialized),
                    "inserted_messages": inserted,
                    "deduplicated_messages": deduplicated,
                    "conversations_seen": len(conversation_keys),
                    "requested_attachments": len(attachment_materialized),
                    "inserted_attachments": attachments_inserted,
                    "deduplicated_attachments": attachments_deduplicated,
                    "canonical_records_changed": 0,
                    "production_import": mode == "production",
                    "idempotent_replay": False,
                    "verified": actual,
                }
                connection.execute(
                    "UPDATE history_import_runs SET completed_at=?,status='completed',"
                    "stats_json=?,canonical_records_changed=0,production_import=? "
                    "WHERE run_id=?",
                    (
                        self._now(),
                        json.dumps(stats, sort_keys=True),
                        int(mode == "production"),
                        run_id,
                    ),
                )
            return stats
        except Exception as exc:
            # Closing the failed transaction rolls back all source, conversation,
            # message, attachment, and FTS writes.  Preserve only a content-free
            # failure record in a separate transaction for auditability.
            with self._connect() as connection:
                connection.execute(
                    "INSERT INTO history_import_runs("
                    "run_id,created_at,completed_at,source_platform,source_set_id,"
                    "source_manifest_sha256,mode,status,stats_json,"
                    "canonical_records_changed,production_import,error) "
                    "VALUES (?,?,?,?,?,?,?,'rolled_back','{}',0,?,?) "
                    "ON CONFLICT(run_id) DO UPDATE SET completed_at=excluded.completed_at,"
                    "mode=excluded.mode,status='rolled_back',stats_json='{}',"
                    "canonical_records_changed=0,"
                    "production_import=excluded.production_import,error=excluded.error",
                    (
                        run_id,
                        now,
                        self._now(),
                        str(self._history_field(materialized[0], "source_platform")),
                        source_set_id,
                        manifest_sha256,
                        mode,
                        int(mode == "production"),
                        str(exc)[:500],
                    ),
                )
            raise

    def search_history(
        self,
        query: str,
        *,
        limit: int = 20,
        source_platform: str | None = None,
        speaker: str | None = None,
        start_at: str | None = None,
        end_at: str | None = None,
        conversation_title: str | None = None,
    ) -> list[dict[str, object]]:
        clean_query = query.strip()
        if not clean_query or len(clean_query) > 500:
            raise ValueError("Historical search query must contain 1 to 500 characters")
        if limit < 1 or limit > 100:
            raise ValueError("Historical search limit must be between 1 and 100")
        phrase = '"' + clean_query.replace('"', '""') + '"'
        clauses = ["history_messages_fts MATCH ?"]
        values: list[object] = [phrase]
        for column, value in (
            ("h.source_platform", source_platform),
            ("h.speaker", speaker),
            ("h.conversation_title", conversation_title),
        ):
            if value is not None:
                clauses.append(f"{column}=?")
                values.append(value)
        if start_at is not None:
            clauses.append("h.timestamp>=?")
            values.append(start_at)
        if end_at is not None:
            clauses.append("h.timestamp<=?")
            values.append(end_at)
        values.append(limit)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT h.stable_id,h.source_platform,h.source_conversation_id,"
                "h.conversation_title,h.source_message_id,h.timestamp,h.speaker,"
                "h.role,h.raw_text,h.source_pointer,h.historical_only,"
                "h.canonical_effect FROM history_messages_fts "
                "JOIN history_messages h ON h.message_id=history_messages_fts.rowid "
                f"WHERE {' AND '.join(clauses)} "
                "ORDER BY h.timestamp DESC,h.message_order DESC LIMIT ?",
                values,
            ).fetchall()
        return [
            {
                **dict(row),
                "evidence_label": "imported_historical_evidence_not_canonical",
            }
            for row in rows
        ]

    def search_history_ranked(
        self,
        terms: list[str] | tuple[str, ...],
        *,
        limit: int = 30,
        source_platform: str | None = None,
        match_all: bool = True,
    ) -> list[dict[str, object]]:
        """Search imported history with a safely constructed FTS expression.

        The existing exact-phrase ``search_history`` behavior remains unchanged.
        Terms, never caller-provided FTS syntax, cross this boundary.
        """
        clean_terms: list[str] = []
        for value in terms:
            for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]{1,63}", str(value)):
                normalized = token.casefold()
                if normalized not in clean_terms:
                    clean_terms.append(normalized)
        if not clean_terms or len(clean_terms) > 12:
            raise ValueError("Historical ranked search requires 1 to 12 safe terms")
        if limit < 1 or limit > 100:
            raise ValueError("Historical search limit must be between 1 and 100")
        operator = " AND " if match_all else " OR "
        expression = operator.join(f'"{term}"' for term in clean_terms)
        clauses = ["history_messages_fts MATCH ?"]
        values: list[object] = [expression]
        if source_platform is not None:
            clauses.append("h.source_platform=?")
            values.append(source_platform)
        values.append(limit)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT h.message_id,h.stable_id,h.source_platform,"
                "h.source_conversation_id,h.conversation_id,h.conversation_title,"
                "h.source_message_id,h.timestamp,h.speaker,h.role,h.raw_text,"
                "h.message_order,h.source_pointer,h.historical_only,h.canonical_effect,"
                "bm25(history_messages_fts) AS relevance_rank "
                "FROM history_messages_fts JOIN history_messages h "
                "ON h.message_id=history_messages_fts.rowid "
                f"WHERE {' AND '.join(clauses)} "
                "ORDER BY relevance_rank,h.timestamp LIMIT ?",
                values,
            ).fetchall()
        return [
            {
                **dict(row),
                "evidence_label": "imported_historical_evidence_not_canonical",
            }
            for row in rows
        ]

    def history_message_window(
        self, message_id: int, *, before: int = 1, after: int = 2
    ) -> list[dict[str, object]]:
        if before < 0 or after < 0 or before > 10 or after > 10:
            raise ValueError("Historical message window must be between 0 and 10")
        with self._connect() as connection:
            anchor = connection.execute(
                "SELECT conversation_id,message_order FROM history_messages WHERE message_id=?",
                (message_id,),
            ).fetchone()
            if anchor is None or anchor["conversation_id"] is None:
                return []
            rows = connection.execute(
                "SELECT message_id,stable_id,source_platform,source_conversation_id,"
                "conversation_id,conversation_title,source_message_id,timestamp,speaker,"
                "role,raw_text,message_order,source_pointer,historical_only,canonical_effect "
                "FROM history_messages WHERE conversation_id=? AND message_order BETWEEN ? AND ? "
                "ORDER BY message_order",
                (
                    anchor["conversation_id"],
                    int(anchor["message_order"]) - before,
                    int(anchor["message_order"]) + after,
                ),
            ).fetchall()
        return [
            {
                **dict(row),
                "evidence_label": "imported_historical_evidence_not_canonical",
            }
            for row in rows
        ]

    def record_retrieval_event(
        self,
        *,
        request_id: str,
        query: str,
        trigger_reason: str,
        question_domain: str,
        query_terms: list[str],
        entity_candidates: list[str],
        source_types: list[str],
        evidence_ids: list[str],
        knowledge_state: str,
        exclusions: list[str],
        packet_chars: int,
        failure_classification: str | None,
        delivery_status: str = "built",
    ) -> None:
        if knowledge_state not in {
            "VERIFIED", "CANONICAL", "RETRIEVED", "INFERRED", "UNKNOWN", "CONFLICT"
        }:
            raise ValueError("Invalid retrieval knowledge state")
        if delivery_status not in {"built", "injected", "unavailable"}:
            raise ValueError("Invalid retrieval delivery status")
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO retrieval_events("
                "request_id,created_at,query_sha256,trigger_reason,question_domain,"
                "query_terms_json,entity_candidates_json,source_types_json,"
                "evidence_ids_json,knowledge_state,exclusions_json,packet_chars,"
                "failure_classification,delivery_status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(request_id) DO UPDATE SET "
                "trigger_reason=excluded.trigger_reason,question_domain=excluded.question_domain,"
                "query_terms_json=excluded.query_terms_json,"
                "entity_candidates_json=excluded.entity_candidates_json,"
                "source_types_json=excluded.source_types_json,"
                "evidence_ids_json=excluded.evidence_ids_json,"
                "knowledge_state=excluded.knowledge_state,"
                "exclusions_json=excluded.exclusions_json,packet_chars=excluded.packet_chars,"
                "failure_classification=excluded.failure_classification,"
                "delivery_status=excluded.delivery_status",
                (
                    request_id,
                    self._now(),
                    hashlib.sha256(query.encode("utf-8")).hexdigest(),
                    trigger_reason,
                    question_domain,
                    json.dumps(query_terms, ensure_ascii=False),
                    json.dumps(entity_candidates, ensure_ascii=False),
                    json.dumps(source_types, ensure_ascii=False),
                    json.dumps(evidence_ids, ensure_ascii=False),
                    knowledge_state,
                    json.dumps(exclusions, ensure_ascii=False),
                    packet_chars,
                    failure_classification,
                    delivery_status,
                ),
            )

    def mark_retrieval_injected(self, request_id: str, packet_sha256: str) -> bool:
        if not re.fullmatch(r"[0-9a-f]{64}", packet_sha256):
            raise ValueError("Retrieval packet checksum is invalid")
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE retrieval_events SET delivery_status='injected',packet_sha256=? "
                "WHERE request_id=?",
                (packet_sha256, request_id),
            )
        return cursor.rowcount == 1

    def retrieval_events(self, *, limit: int = 50) -> list[dict[str, object]]:
        if limit < 1 or limit > 500:
            raise ValueError("Retrieval event limit must be between 1 and 500")
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM retrieval_events ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def conversation_history(
        self,
        *,
        source_platform: str,
        source_conversation_id: str,
        limit: int = 1000,
    ) -> list[dict[str, object]]:
        if not source_platform.strip() or not source_conversation_id.strip():
            raise ValueError("Historical conversation source and ID are required")
        if limit < 1 or limit > 5000:
            raise ValueError("Historical conversation limit must be between 1 and 5000")
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT stable_id,source_platform,source_conversation_id,"
                "conversation_title,source_message_id,timestamp,speaker,role,raw_text,"
                "message_order,source_pointer,historical_only,canonical_effect "
                "FROM history_messages WHERE source_platform=? "
                "AND source_conversation_id=? ORDER BY message_order,timestamp LIMIT ?",
                (source_platform, source_conversation_id, limit),
            ).fetchall()
        return [
            {
                **dict(row),
                "evidence_label": "imported_historical_evidence_not_canonical",
            }
            for row in rows
        ]

    def record_subscription_consultation(
        self,
        *,
        request_id: str,
        provider: str,
        user_query: str,
        rendered_prompt: str | None,
        invocation_attempted: bool,
        status: str,
        response: str,
        error: str | None,
    ) -> dict[str, object]:
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO subscription_consultations("
                "created_at,request_id,provider,user_query,rendered_prompt,"
                "invocation_attempted,status,response,error) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    self._now(),
                    request_id,
                    provider,
                    user_query,
                    rendered_prompt,
                    int(invocation_attempted),
                    status,
                    response,
                    error,
                ),
            )
        record = self.subscription_consultation(request_id)
        if record is None:
            raise RuntimeError("Consultation evidence record was not persisted")
        return record

    def subscription_consultation(self, request_id: str) -> dict[str, object] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id,created_at,request_id,provider,user_query,rendered_prompt,"
                "invocation_attempted,status,response,error "
                "FROM subscription_consultations WHERE request_id=?",
                (request_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "id": int(row["id"]),
            "created_at": row["created_at"],
            "request_id": row["request_id"],
            "provider": row["provider"],
            "user_query": row["user_query"],
            "rendered_prompt": row["rendered_prompt"],
            "invocation_attempted": bool(row["invocation_attempted"]),
            "status": row["status"],
            "response": row["response"],
            "error": row["error"],
        }

    def recent_subscription_consultations(
        self, *, limit: int = 20
    ) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT request_id FROM subscription_consultations "
                "ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        records = [self.subscription_consultation(row["request_id"]) for row in rows]
        return [record for record in records if record is not None]

    @staticmethod
    def _maintenance_record(row: sqlite3.Row) -> dict[str, object]:
        return {
            "id": int(row["id"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "request_id": row["request_id"],
            "user_request": row["user_request"],
            "operation": row["operation"],
            "target_path": row["target_path"],
            "status": row["status"],
            "base_branch": row["base_branch"],
            "maintenance_branch": row["maintenance_branch"],
            "base_commit": row["base_commit"],
            "files_read": json.loads(row["files_read_json"]),
            "files_changed": json.loads(row["files_changed_json"]),
            "commands": json.loads(row["commands_json"]),
            "diff_summary": row["diff_summary"],
            "tests": json.loads(row["tests_json"]),
            "consultants": json.loads(row["consultants_json"]),
            "final_commit": row["final_commit"],
            "rollback_result": row["rollback_result"],
            "approval_required": bool(row["approval_required"]),
            "error": row["error"],
        }

    def create_maintenance_job(
        self,
        *,
        request_id: str,
        user_request: str,
        operation: str,
        target_path: str,
        consultants: list[dict[str, object]],
    ) -> int:
        now = self._now()
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO maintenance_jobs("
                "created_at,updated_at,request_id,user_request,operation,target_path,"
                "consultants_json) VALUES (?,?,?,?,?,?,?)",
                (
                    now,
                    now,
                    request_id,
                    user_request,
                    operation,
                    target_path,
                    json.dumps(consultants, sort_keys=True),
                ),
            )
            return int(cursor.lastrowid)

    def update_maintenance_job(self, job_id: int, **changes: object) -> None:
        allowed = {
            "status",
            "base_branch",
            "maintenance_branch",
            "base_commit",
            "files_read",
            "files_changed",
            "commands",
            "diff_summary",
            "tests",
            "consultants",
            "final_commit",
            "rollback_result",
            "approval_required",
            "error",
        }
        unknown = set(changes) - allowed
        if unknown:
            raise ValueError(f"Unsupported maintenance fields: {sorted(unknown)}")
        if not changes:
            return
        json_fields = {
            "files_read": "files_read_json",
            "files_changed": "files_changed_json",
            "commands": "commands_json",
            "tests": "tests_json",
            "consultants": "consultants_json",
        }
        assignments = ["updated_at=?"]
        values: list[object] = [self._now()]
        for key, value in changes.items():
            column = json_fields.get(key, key)
            assignments.append(f"{column}=?")
            if key in json_fields:
                values.append(json.dumps(value, sort_keys=True))
            elif key == "approval_required":
                values.append(int(bool(value)))
            else:
                values.append(value)
        values.append(job_id)
        with self._connect() as connection:
            cursor = connection.execute(
                f"UPDATE maintenance_jobs SET {','.join(assignments)} WHERE id=?",
                values,
            )
            if cursor.rowcount != 1:
                raise ValueError("Maintenance job was not found")

    def maintenance_job(self, request_id: str) -> dict[str, object] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM maintenance_jobs WHERE request_id=?", (request_id,)
            ).fetchone()
        return None if row is None else self._maintenance_record(row)

    def recent_maintenance_jobs(self, limit: int = 20) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM maintenance_jobs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._maintenance_record(row) for row in rows]

    def add_maintenance_event(
        self, *, job_id: int, event: str, detail: dict[str, object]
    ) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO maintenance_events(created_at,job_id,event,detail_json) "
                "VALUES (?,?,?,?)",
                (self._now(), job_id, event, json.dumps(detail, sort_keys=True)),
            )
            return int(cursor.lastrowid)

    def maintenance_events(self, job_id: int) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id,created_at,event,detail_json FROM maintenance_events "
                "WHERE job_id=? ORDER BY id",
                (job_id,),
            ).fetchall()
        return [
            {
                "id": int(row["id"]),
                "created_at": row["created_at"],
                "event": row["event"],
                "detail": json.loads(row["detail_json"]),
            }
            for row in rows
        ]

    def remember(self, content: str) -> int:
        with self._connect() as connection:
            cursor = connection.execute("INSERT INTO memories(created_at,content) VALUES (?,?)", (self._now(), content))
            return int(cursor.lastrowid)

    def memories(self) -> list[tuple[int, str]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id,content FROM memories WHERE status='active' ORDER BY id"
            ).fetchall()
        return [(int(row["id"]), row["content"]) for row in rows]

    def memory_records(self) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id,created_at,updated_at,content,status FROM memories ORDER BY id"
            ).fetchall()
        return [dict(row) for row in rows]

    def request_memory_change(
        self, *, memory_id: int, action: str, replacement_content: str | None = None
    ) -> tuple[int, int]:
        if action not in {"correct", "delete", "restore"}:
            raise ValueError("Memory action must be correct, delete, or restore")
        replacement = replacement_content.strip() if replacement_content is not None else None
        if action == "correct" and (not replacement or len(replacement) > 2_000):
            raise ValueError("A correction must contain between 1 and 2000 characters")
        if action != "correct" and replacement is not None:
            raise ValueError("Only a correction may include replacement content")
        with self._connect() as connection:
            memory = connection.execute(
                "SELECT content,status FROM memories WHERE id=?", (memory_id,)
            ).fetchone()
            if memory is None:
                raise ValueError("Memory was not found")
            current_status = str(memory["status"])
            if action in {"correct", "delete"} and current_status != "active":
                raise ValueError("Only an active memory may be corrected or deleted")
            if action == "restore" and current_status != "archived":
                raise ValueError("Only an archived memory may be restored")
            duplicate = connection.execute(
                "SELECT id FROM memory_changes WHERE memory_id=? AND status='pending_review'",
                (memory_id,),
            ).fetchone()
            if duplicate is not None:
                raise ValueError("A memory change is already awaiting review")
            description = f"{action} local memory {memory_id}"
            approval = connection.execute(
                "INSERT INTO approvals(created_at,description) VALUES (?,?)",
                (self._now(), description),
            )
            approval_id = int(approval.lastrowid)
            change = connection.execute(
                "INSERT INTO memory_changes(created_at,memory_id,action,replacement_content,approval_id) "
                "VALUES (?,?,?,?,?)",
                (self._now(), memory_id, action, replacement, approval_id),
            )
            change_id = int(change.lastrowid)
        self.audit("memory_change_requested", f"{change_id}: {action} memory {memory_id}")
        self.audit("approval_requested", f"{approval_id}: {description}")
        return change_id, approval_id

    def memory_changes(self, *, pending_only: bool = False) -> list[dict[str, object]]:
        query = (
            "SELECT c.id,c.memory_id,c.action,c.replacement_content,c.status,c.approval_id,"
            "a.status approval_status FROM memory_changes c "
            "JOIN approvals a ON a.id=c.approval_id"
        )
        if pending_only:
            query += " WHERE c.status='pending_review'"
        query += " ORDER BY c.id"
        with self._connect() as connection:
            rows = connection.execute(query).fetchall()
        return [dict(row) for row in rows]

    def apply_memory_change(self, change_id: int) -> dict[str, object]:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            change = connection.execute(
                "SELECT c.*,a.status approval_status FROM memory_changes c "
                "JOIN approvals a ON a.id=c.approval_id WHERE c.id=?",
                (change_id,),
            ).fetchone()
            if change is None or change["status"] != "pending_review":
                raise ValueError("Pending memory change was not found")
            if change["approval_status"] != "approved":
                raise ValueError("Memory change requires an approved review record")
            memory = connection.execute(
                "SELECT content,status FROM memories WHERE id=?", (change["memory_id"],)
            ).fetchone()
            if memory is None:
                raise ValueError("Memory was not found")
            action = str(change["action"])
            if action == "correct":
                if memory["status"] != "active":
                    raise ValueError("Only an active memory may be corrected")
                connection.execute(
                    "UPDATE memories SET content=?,updated_at=? WHERE id=?",
                    (change["replacement_content"], self._now(), change["memory_id"]),
                )
            elif action == "delete":
                if memory["status"] != "active":
                    raise ValueError("Only an active memory may be deleted")
                connection.execute(
                    "UPDATE memories SET status='archived',updated_at=? WHERE id=?",
                    (self._now(), change["memory_id"]),
                )
            else:
                if memory["status"] != "archived":
                    raise ValueError("Only an archived memory may be restored")
                connection.execute(
                    "UPDATE memories SET status='active',updated_at=? WHERE id=?",
                    (self._now(), change["memory_id"]),
                )
            connection.execute(
                "UPDATE memory_changes SET status='applied',applied_at=?,original_content=? WHERE id=?",
                (self._now(), memory["content"], change_id),
            )
        self.audit("memory_change_applied", f"{change_id}: {action} memory {change['memory_id']}")
        return {
            "change_id": change_id,
            "memory_id": int(change["memory_id"]),
            "action": action,
            "status": "applied",
            "hard_delete": False,
        }

    def record_model_proposal(self, *, user_input: str, model: str, response_json: str) -> int:
        if len(user_input) > 4_000 or len(response_json) > 20_000:
            raise ValueError("Model proposal record is too large")
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO model_proposals(created_at,user_input,model,response_json) VALUES (?,?,?,?)",
                (self._now(), user_input, model, response_json),
            )
            proposal_id = int(cursor.lastrowid)
        self.audit("model_proposal_recorded", f"{proposal_id}: {model}")
        return proposal_id

    def recent_model_proposals(self, limit: int = 20) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id,created_at,model,response_json,status,decided_at,decision_reason "
                "FROM model_proposals "
                "ORDER BY id DESC LIMIT ?", (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def record_external_proposal(
        self, *, external_id: str, source: str, kind: str, summary: str,
        external_created_at: str,
    ) -> dict[str, object]:
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO external_proposals("
                "received_at,external_id,external_created_at,source,kind,summary"
                ") VALUES (?,?,?,?,?,?)",
                (self._now(), external_id, external_created_at, source, kind, summary),
            )
            inserted = cursor.rowcount == 1
            row = connection.execute(
                "SELECT id FROM external_proposals WHERE external_id=?", (external_id,)
            ).fetchone()
        if inserted:
            self.audit("external_proposal_recorded", f"{row['id']}: {kind}")
        return {"id": int(row["id"]), "inserted": inserted}

    def recent_external_proposals(self, limit: int = 20) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id,received_at,external_id,source,kind,summary,status,"
                "decided_at,decision_reason "
                "FROM external_proposals ORDER BY id DESC LIMIT ?", (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def decide_proposal(
        self, *, proposal_type: str, proposal_id: int, decision: str, reason: str
    ) -> dict[str, object]:
        tables = {"external": "external_proposals", "model": "model_proposals"}
        if proposal_type not in tables:
            raise ValueError("Proposal type must be external or model")
        statuses = {"accept": "accepted", "reject": "rejected"}
        if decision not in statuses:
            raise ValueError("Decision must be accept or reject")
        clean_reason = reason.strip()
        if not clean_reason or len(clean_reason) > 500:
            raise ValueError("Decision reason must contain 1 to 500 characters")
        with self._connect() as connection:
            cursor = connection.execute(
                f"UPDATE {tables[proposal_type]} "
                "SET status=?,decided_at=?,decision_reason=? "
                "WHERE id=? AND status='review_required'",
                (statuses[decision], self._now(), clean_reason, proposal_id),
            )
            changed = cursor.rowcount == 1
        if changed:
            self.audit(
                "proposal_reviewed",
                f"{proposal_type} {proposal_id}: {statuses[decision]}; no execution",
            )
        return {
            "status": statuses[decision] if changed else "not_found_or_already_reviewed",
            "proposal_type": proposal_type,
            "proposal_id": proposal_id,
            "actions_queued": 0,
            "actions_executed": 0,
            "external_activity": False,
        }

    def proposal_review_summary(self) -> dict[str, object]:
        with self._connect() as connection:
            counts: dict[str, dict[str, int]] = {}
            for label, table in (
                ("external", "external_proposals"),
                ("model", "model_proposals"),
                ("repair", "repair_proposals"),
            ):
                rows = connection.execute(
                    f"SELECT status,COUNT(*) total FROM {table} GROUP BY status"
                ).fetchall()
                counts[label] = {str(row["status"]): int(row["total"]) for row in rows}
        return {
            "counts": counts,
            "review_required": sum(
                group.get("review_required", 0) for group in counts.values()
            ),
            "external": self.recent_external_proposals(),
            "model": self.recent_model_proposals(),
            "actions_queued": 0,
            "actions_executed": 0,
        }

    @staticmethod
    def _bounded_handoff_text(value: str, *, label: str) -> str:
        clean = value.strip()
        if not clean or len(clean) > 4_000:
            raise ValueError(f"{label} must contain 1 to 4000 characters")
        lowered = clean.lower()
        secret_markers = (
            "sk-", "aizasy", "bearer ", "api_key=", "api-key:",
            "-----begin private key-----", "-----begin rsa private key-----",
        )
        if any(marker in lowered for marker in secret_markers):
            raise ValueError(f"{label} appears to contain a credential")
        return clean

    def create_model_handoff(self, *, target: str, request: str) -> dict[str, object]:
        clean_target = target.strip().lower()
        if clean_target not in {"sophie", "bernie"}:
            raise ValueError("Handoff target must be Sophie or Bernie")
        clean_request = self._bounded_handoff_text(request, label="Handoff request")
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO model_handoffs(created_at,target,request) VALUES (?,?,?)",
                (self._now(), clean_target, clean_request),
            )
            handoff_id = int(cursor.lastrowid)
        self.audit("model_handoff_drafted", f"{handoff_id}: {clean_target}")
        return self.model_handoff(handoff_id)

    def model_handoff(self, handoff_id: int) -> dict[str, object]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id,created_at,target,request,status,response,answered_at,"
                "api_budget_cents,manual_relay_required,external_activity,response_untrusted "
                "FROM model_handoffs WHERE id=?", (handoff_id,),
            ).fetchone()
        if row is None:
            raise ValueError("Model handoff was not found")
        record = dict(row)
        for key in ("manual_relay_required", "external_activity", "response_untrusted"):
            record[key] = bool(record[key])
        return record

    def recent_model_handoffs(self, limit: int = 20) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id,created_at,target,request,status,api_budget_cents,"
                "manual_relay_required,external_activity,response_untrusted "
                "FROM model_handoffs ORDER BY id DESC LIMIT ?", (limit,),
            ).fetchall()
        records = [dict(row) for row in rows]
        for record in records:
            for key in ("manual_relay_required", "external_activity", "response_untrusted"):
                record[key] = bool(record[key])
        return records

    def record_model_handoff_answer(self, *, handoff_id: int, response: str) -> bool:
        clean_response = self._bounded_handoff_text(response, label="Handoff response")
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE model_handoffs SET status='answered',response=?,answered_at=? "
                "WHERE id=? AND status='draft'",
                (clean_response, self._now(), handoff_id),
            )
            changed = cursor.rowcount == 1
        if changed:
            self.audit("model_handoff_answer_recorded", str(handoff_id))
        return changed

    def add_task(self, description: str) -> int:
        with self._connect() as connection:
            cursor = connection.execute("INSERT INTO tasks(created_at,description) VALUES (?,?)", (self._now(), description))
            return int(cursor.lastrowid)

    def pending_tasks(self) -> list[tuple[int, str]]:
        with self._connect() as connection:
            rows = connection.execute("SELECT id,description FROM tasks WHERE status='pending' ORDER BY id").fetchall()
        return [(int(row["id"]), row["description"]) for row in rows]

    def complete_task(self, task_id: int) -> bool:
        with self._connect() as connection:
            cursor = connection.execute("UPDATE tasks SET status='complete' WHERE id=? AND status='pending'", (task_id,))
            return cursor.rowcount == 1

    def counts(self) -> dict[str, int]:
        with self._connect() as connection:
            memories = connection.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
            pending = connection.execute("SELECT COUNT(*) FROM tasks WHERE status='pending'").fetchone()[0]
            messages = connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
            approvals = connection.execute("SELECT COUNT(*) FROM approvals WHERE status='pending'").fetchone()[0]
            reminders = connection.execute("SELECT COUNT(*) FROM reminders WHERE status='pending'").fetchone()[0]
            learning_units = connection.execute("SELECT COUNT(*) FROM learning_units").fetchone()[0]
            completed_learning_units = connection.execute(
                "SELECT COUNT(*) FROM learning_units WHERE status='complete'"
            ).fetchone()[0]
        return {
            "memories": int(memories), "pending_tasks": int(pending),
            "messages": int(messages), "pending_approvals": int(approvals),
            "pending_reminders": int(reminders),
            "learning_units": int(learning_units),
            "completed_learning_units": int(completed_learning_units),
        }

    @staticmethod
    def _learning_text(value: object, *, label: str, maximum: int) -> str:
        if not isinstance(value, str):
            raise ValueError(f"{label} must be text")
        clean = value.strip()
        if not clean or len(clean) > maximum:
            raise ValueError(f"{label} must contain 1 to {maximum} characters")
        return clean

    def upsert_learning_unit(self, record: dict[str, object]) -> dict[str, object]:
        required = {
            "learning_id", "curriculum_version", "unit_digest", "track", "title",
            "objective", "status", "authority", "budgets", "sources", "evidence",
            "claims", "contradictions", "corrections", "assessment", "capability_change",
        }
        if set(record) != required:
            raise ValueError("Learning unit fields do not match the governed schema")
        learning_id = self._learning_text(
            record["learning_id"], label="Learning ID", maximum=64
        ).upper()
        if any(character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for character in learning_id):
            raise ValueError("Learning ID contains unsupported characters")
        status = self._learning_text(record["status"], label="Learning status", maximum=32)
        if status not in {"prepared", "complete", "attention_required"}:
            raise ValueError("Learning status is invalid")
        capability_change = self._learning_text(
            record["capability_change"], label="Capability change", maximum=32
        )
        if capability_change != "none":
            raise ValueError("A learning unit cannot grant capability")
        unit_digest = self._learning_text(
            record["unit_digest"], label="Unit digest", maximum=64
        ).lower()
        if len(unit_digest) != 64 or any(character not in "0123456789abcdef" for character in unit_digest):
            raise ValueError("Unit digest must be a SHA-256 value")
        text_fields = {
            "curriculum_version": self._learning_text(
                record["curriculum_version"], label="Curriculum version", maximum=32
            ),
            "track": self._learning_text(record["track"], label="Learning track", maximum=64),
            "title": self._learning_text(record["title"], label="Learning title", maximum=200),
            "objective": self._learning_text(
                record["objective"], label="Learning objective", maximum=1_000
            ),
            "authority": self._learning_text(
                record["authority"], label="Learning authority", maximum=500
            ),
        }
        json_fields: dict[str, str] = {}
        for key in (
            "budgets", "sources", "evidence", "claims", "contradictions",
            "corrections", "assessment",
        ):
            encoded = json.dumps(record[key], separators=(",", ":"), sort_keys=True)
            if len(encoded) > 100_000:
                raise ValueError(f"Learning {key} exceeds the storage limit")
            json_fields[f"{key}_json"] = encoded
        now = self._now()
        version_record = {
            "learning_id": learning_id,
            "curriculum_version": text_fields["curriculum_version"],
            "unit_digest": unit_digest,
            "track": text_fields["track"],
            "title": text_fields["title"],
            "objective": text_fields["objective"],
            "status": status,
            "authority": text_fields["authority"],
            "budgets": record["budgets"],
            "sources": record["sources"],
            "evidence": record["evidence"],
            "claims": record["claims"],
            "contradictions": record["contradictions"],
            "corrections": record["corrections"],
            "assessment": record["assessment"],
            "capability_change": capability_change,
        }
        version_json = json.dumps(version_record, separators=(",", ":"), sort_keys=True)
        if len(version_json) > 500_000:
            raise ValueError("Learning unit version exceeds the storage limit")
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT unit_digest,status FROM learning_units WHERE learning_id=?",
                (learning_id,),
            ).fetchone()
            changed = existing is None or (
                str(existing["unit_digest"]) != unit_digest
                or str(existing["status"]) != status
            )
            if changed:
                connection.execute(
                    """
                    INSERT INTO learning_units(
                        learning_id,created_at,updated_at,curriculum_version,unit_digest,
                        track,title,objective,status,authority,budgets_json,sources_json,
                        evidence_json,claims_json,contradictions_json,corrections_json,
                        assessment_json,capability_change
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(learning_id) DO UPDATE SET
                        updated_at=excluded.updated_at,
                        curriculum_version=excluded.curriculum_version,
                        unit_digest=excluded.unit_digest,
                        track=excluded.track,title=excluded.title,objective=excluded.objective,
                        status=excluded.status,authority=excluded.authority,
                        budgets_json=excluded.budgets_json,sources_json=excluded.sources_json,
                        evidence_json=excluded.evidence_json,claims_json=excluded.claims_json,
                        contradictions_json=excluded.contradictions_json,
                        corrections_json=excluded.corrections_json,
                        assessment_json=excluded.assessment_json,
                        capability_change=excluded.capability_change
                    """,
                    (
                        learning_id, now, now, text_fields["curriculum_version"],
                        unit_digest, text_fields["track"], text_fields["title"],
                        text_fields["objective"], status, text_fields["authority"],
                        json_fields["budgets_json"], json_fields["sources_json"],
                        json_fields["evidence_json"], json_fields["claims_json"],
                        json_fields["contradictions_json"], json_fields["corrections_json"],
                        json_fields["assessment_json"], capability_change,
                    ),
                )
            version_cursor = connection.execute(
                "INSERT OR IGNORE INTO learning_unit_versions("
                "learning_id,recorded_at,curriculum_version,unit_digest,status,record_json"
                ") VALUES (?,?,?,?,?,?)",
                (
                    learning_id, now, text_fields["curriculum_version"], unit_digest,
                    status, version_json,
                ),
            )
            version_added = version_cursor.rowcount == 1
        if changed:
            self.audit("learning_unit_synced", f"{learning_id}: {status}")
        elif version_added:
            self.audit("learning_version_backfilled", learning_id)
        return {
            **self.learning_unit(learning_id),
            "changed": changed,
            "version_added": version_added,
        }

    def learning_unit(self, learning_id: str) -> dict[str, object]:
        clean_id = learning_id.strip().upper()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM learning_units WHERE learning_id=?", (clean_id,)
            ).fetchone()
        if row is None:
            raise ValueError("Learning unit was not found")
        record = dict(row)
        for key in (
            "budgets", "sources", "evidence", "claims", "contradictions",
            "corrections", "assessment",
        ):
            record[key] = json.loads(str(record.pop(f"{key}_json")))
        return record

    def learning_units(self) -> list[dict[str, object]]:
        with self._connect() as connection:
            ids = [
                str(row["learning_id"])
                for row in connection.execute(
                    "SELECT learning_id FROM learning_units ORDER BY learning_id"
                ).fetchall()
            ]
        return [self.learning_unit(learning_id) for learning_id in ids]

    def record_learning_model_assessment(
        self, record: dict[str, object]
    ) -> dict[str, object]:
        required = {
            "curriculum_version", "curriculum_sha256", "protocol_version", "model", "request_digest",
            "status", "score", "total", "answers", "error", "output_untrusted",
            "external_activity", "api_spending_cents", "local_model_requests",
            "capability_change",
        }
        if set(record) != required:
            raise ValueError("Learning model assessment fields do not match the governed schema")
        if record["output_untrusted"] is not True:
            raise ValueError("Learning model output must remain untrusted")
        if record["external_activity"] is not False or record["api_spending_cents"] != 0:
            raise ValueError("Learning model assessment must remain local and zero-spend")
        if record["capability_change"] != "none":
            raise ValueError("Learning model assessment cannot grant capability")
        local_requests = record["local_model_requests"]
        if not isinstance(local_requests, int) or local_requests not in {0, 1}:
            raise ValueError("Learning model assessment request count is invalid")
        status = self._learning_text(
            record["status"], label="Learning model assessment status", maximum=32
        )
        if status not in {"passed", "needs_review", "error"}:
            raise ValueError("Learning model assessment status is invalid")
        score = record["score"]
        total = record["total"]
        if (
            not isinstance(score, int)
            or not isinstance(total, int)
            or total < 1
            or score < 0
            or score > total
        ):
            raise ValueError("Learning model assessment score is invalid")
        answers = record["answers"]
        if not isinstance(answers, list):
            raise ValueError("Learning model assessment answers must be a list")
        answers_json = json.dumps(answers, separators=(",", ":"), sort_keys=True)
        if len(answers_json) > 100_000:
            raise ValueError("Learning model assessment answers exceed the storage limit")
        error = record["error"]
        if error is not None:
            error = self._learning_text(error, label="Learning model assessment error", maximum=500)
        if status == "error" and error is None:
            raise ValueError("Failed learning model assessment requires an error record")
        if status != "error" and error is not None:
            raise ValueError("Successful learning model assessment cannot include an error")
        hashes: dict[str, str] = {}
        for key in ("curriculum_sha256", "request_digest"):
            value = self._learning_text(record[key], label=key, maximum=64).lower()
            if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
                raise ValueError(f"{key} must be a SHA-256 value")
            hashes[key] = value
        curriculum_version = self._learning_text(
            record["curriculum_version"], label="Curriculum version", maximum=32
        )
        protocol_version = self._learning_text(
            record["protocol_version"], label="Assessment protocol", maximum=64
        )
        model = self._learning_text(record["model"], label="Local model", maximum=200)
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO learning_model_assessments("
                "created_at,curriculum_version,curriculum_sha256,protocol_version,model,request_digest,"
                "status,score,total,answers_json,error_text,output_untrusted,external_activity,"
                "api_spending_cents,local_model_requests,capability_change"
                ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    self._now(), curriculum_version, hashes["curriculum_sha256"],
                    protocol_version, model,
                    hashes["request_digest"], status, score, total, answers_json, error,
                    1, 0, 0, local_requests, "none",
                ),
            )
            assessment_id = int(cursor.lastrowid)
        self.audit(
            "learning_model_assessment_recorded",
            f"{assessment_id}: {status} {score}/{total}; output untrusted",
        )
        return self.learning_model_assessment(assessment_id)

    def learning_model_assessment(self, assessment_id: int) -> dict[str, object]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM learning_model_assessments WHERE assessment_id=?",
                (assessment_id,),
            ).fetchone()
        if row is None:
            raise ValueError("Learning model assessment was not found")
        record = dict(row)
        record["answers"] = json.loads(str(record.pop("answers_json")))
        for key in ("output_untrusted", "external_activity"):
            record[key] = bool(record[key])
        return record

    def learning_model_assessments(self, limit: int = 20) -> list[dict[str, object]]:
        if not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("Learning model assessment limit must be 1 to 100")
        with self._connect() as connection:
            ids = [
                int(row["assessment_id"])
                for row in connection.execute(
                    "SELECT assessment_id FROM learning_model_assessments "
                    "ORDER BY assessment_id DESC LIMIT ?", (limit,)
                ).fetchall()
            ]
        return [self.learning_model_assessment(assessment_id) for assessment_id in ids]

    def learning_summary(self) -> dict[str, object]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT status,COUNT(*) total FROM learning_units GROUP BY status"
            ).fetchall()
            version_count = int(
                connection.execute("SELECT COUNT(*) FROM learning_unit_versions").fetchone()[0]
            )
            model_assessment_count = int(
                connection.execute("SELECT COUNT(*) FROM learning_model_assessments").fetchone()[0]
            )
        counts = {status: 0 for status in ("prepared", "complete", "attention_required")}
        counts.update({str(row["status"]): int(row["total"]) for row in rows})
        latest_assessments = self.learning_model_assessments(limit=1)
        return {
            "status": "ok" if counts["attention_required"] == 0 else "attention_required",
            "units_total": sum(counts.values()),
            "version_records": version_count,
            "model_assessments_total": model_assessment_count,
            "latest_model_assessment": latest_assessments[0] if latest_assessments else None,
            "units_by_status": counts,
            "capability_change": "none",
            "external_activity": False,
            "api_spending_cents": 0,
            "actions_queued": 0,
            "actions_executed": 0,
        }

    def audit(self, event: str, detail: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO audit(created_at,event,detail) VALUES (?,?,?)",
                (self._now(), event, detail),
            )

    def recent_activity(self, limit: int = 10) -> list[tuple[str, str, str]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT created_at,event,detail FROM audit ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [(row["created_at"], row["event"], row["detail"]) for row in rows]

    def request_approval(self, description: str) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO approvals(created_at,description) VALUES (?,?)",
                (self._now(), description),
            )
            approval_id = int(cursor.lastrowid)
        self.audit("approval_requested", f"{approval_id}: {description}")
        return approval_id

    def pending_approvals(self) -> list[tuple[int, str]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id,description FROM approvals WHERE status='pending' ORDER BY id"
            ).fetchall()
        return [(int(row["id"]), row["description"]) for row in rows]

    def decide_approval(self, approval_id: int, decision: str) -> bool:
        if decision not in {"approved", "denied"}:
            raise ValueError("Decision must be approved or denied")
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE approvals SET status=? WHERE id=? AND status='pending'",
                (decision, approval_id),
            )
            changed = cursor.rowcount == 1
            if changed and decision == "denied":
                connection.execute(
                    "UPDATE memory_changes SET status='denied' "
                    "WHERE approval_id=? AND status='pending_review'",
                    (approval_id,),
                )
        if changed:
            self.audit(f"approval_{decision}", str(approval_id))
        return changed

    def create_daily_backup(self, backup_dir: Path, keep: int = 7) -> Path:
        backup_dir.mkdir(parents=True, exist_ok=True)
        date_stamp = datetime.now().astimezone().strftime("%Y-%m-%d")
        destination = backup_dir / f"josie-{date_stamp}.db"
        if not destination.exists():
            with closing(sqlite3.connect(self.path)) as source, closing(sqlite3.connect(destination)) as target:
                source.backup(target)
            self.audit("database_backup", destination.name)
        backups = sorted(backup_dir.glob("josie-????-??-??.db"), reverse=True)
        for old_backup in backups[max(1, keep):]:
            if old_backup.resolve().parent == backup_dir.resolve():
                old_backup.unlink()
        return destination

    def create_checkpoint_backup(self, backup_dir: Path, label: str = "checkpoint") -> Path:
        clean_label = "".join(character for character in label.lower() if character.isalnum() or character == "-")
        if not clean_label:
            raise ValueError("Checkpoint label is invalid")
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().astimezone().strftime("%Y-%m-%d-%H%M%S-%f")
        destination = backup_dir / f"josie-{stamp}-{clean_label}.db"
        with closing(sqlite3.connect(self.path)) as source, closing(sqlite3.connect(destination)) as target:
            source.backup(target)
        self.audit("database_checkpoint", destination.name)
        return destination

    def add_reminder(self, minutes: int, description: str) -> int:
        due_at = datetime.now(timezone.utc) + timedelta(minutes=minutes)
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO reminders(created_at,due_at,description) VALUES (?,?,?)",
                (self._now(), due_at.isoformat(timespec="seconds"), description),
            )
            reminder_id = int(cursor.lastrowid)
        self.audit("reminder_added", f"{reminder_id}: {description}")
        return reminder_id

    def pending_reminders(self) -> list[tuple[int, str, str]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id,due_at,description FROM reminders WHERE status='pending' ORDER BY due_at"
            ).fetchall()
        return [(int(row["id"]), row["due_at"], row["description"]) for row in rows]

    def deliver_due_reminders(self) -> list[tuple[int, str]]:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id,description FROM reminders WHERE status='pending' AND due_at<=? ORDER BY due_at",
                (now,),
            ).fetchall()
            ids = [int(row["id"]) for row in rows]
            if ids:
                placeholders = ",".join("?" for _ in ids)
                connection.execute(f"UPDATE reminders SET status='delivered' WHERE id IN ({placeholders})", ids)
        for reminder_id in ids:
            self.audit("reminder_delivered", str(reminder_id))
        return [(int(row["id"]), row["description"]) for row in rows]

    def record_ledger_entry(
        self, *, basis: str, category: str, amount: str, description: str
    ) -> int:
        if basis not in {"actual", "estimated"}:
            raise ValueError("Ledger basis must be actual or estimated")
        if category not in {"revenue", "expense", "api_cost", "electricity", "savings"}:
            raise ValueError("Unsupported ledger category")
        if category == "savings" and basis != "estimated":
            raise ValueError("Savings must remain estimated and never count as earned money")
        try:
            decimal_amount = Decimal(amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except InvalidOperation as exc:
            raise ValueError("Amount must be a number") from exc
        if decimal_amount < 0 or decimal_amount > Decimal("1000000000"):
            raise ValueError("Amount is outside the permitted record range")
        cents = int(decimal_amount * 100)
        clean_description = description.strip()
        if not clean_description or len(clean_description) > 500:
            raise ValueError("Description must be between 1 and 500 characters")
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO ledger_entries(created_at,basis,category,amount_cents,description) "
                "VALUES (?,?,?,?,?)",
                (self._now(), basis, category, cents, clean_description),
            )
            entry_id = int(cursor.lastrowid)
        self.audit("ledger_recorded", f"{entry_id}: {basis} {category} {cents} cents")
        return entry_id

    def ledger_summary(self) -> dict[str, int]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT basis,category,COALESCE(SUM(amount_cents),0) total "
                "FROM ledger_entries GROUP BY basis,category"
            ).fetchall()
        totals = {f"{row['basis']}_{row['category']}": int(row["total"]) for row in rows}
        actual_income = totals.get("actual_revenue", 0)
        actual_costs = sum(
            totals.get(f"actual_{category}", 0)
            for category in ("expense", "api_cost", "electricity")
        )
        return {
            "actual_revenue_cents": actual_income,
            "actual_cost_cents": actual_costs,
            "actual_balance_cents": actual_income - actual_costs,
            "estimated_revenue_cents": totals.get("estimated_revenue", 0),
            "estimated_cost_cents": sum(
                totals.get(f"estimated_{category}", 0)
                for category in ("expense", "api_cost", "electricity")
            ),
            "estimated_savings_cents": totals.get("estimated_savings", 0),
        }

    def recent_ledger_entries(self, limit: int = 20) -> list[tuple[int, str, str, int, str]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id,basis,category,amount_cents,description "
                "FROM ledger_entries ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [
            (int(row["id"]), row["basis"], row["category"], int(row["amount_cents"]), row["description"])
            for row in rows
        ]

    @staticmethod
    def _research_text(value: str, *, label: str, maximum: int) -> str:
        clean = value.strip()
        if not clean or len(clean) > maximum:
            raise ValueError(f"{label} must contain 1 to {maximum} characters")
        return clean

    def record_economic_opportunity(
        self,
        *,
        title: str,
        source: str,
        estimated_revenue_cents: int,
        estimated_cost_cents: int,
        estimated_hours_milli: int,
        risk: str,
        notes: str,
    ) -> dict[str, object]:
        clean_title = self._research_text(title, label="Title", maximum=200)
        clean_source = self._research_text(source, label="Source", maximum=300)
        clean_notes = self._research_text(notes, label="Notes", maximum=2_000)
        if risk not in {"low", "medium", "high"}:
            raise ValueError("Risk must be low, medium, or high")
        if (
            type(estimated_revenue_cents) is not int
            or type(estimated_cost_cents) is not int
            or min(estimated_revenue_cents, estimated_cost_cents) < 0
        ):
            raise ValueError("Estimated revenue and cost must be non-negative cents")
        if type(estimated_hours_milli) is not int or estimated_hours_milli <= 0:
            raise ValueError("Estimated hours must be positive")
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO economic_opportunities("
                "created_at,title,source,estimated_revenue_cents,estimated_cost_cents,"
                "estimated_hours_milli,risk,notes) VALUES (?,?,?,?,?,?,?,?)",
                (
                    self._now(), clean_title, clean_source, estimated_revenue_cents,
                    estimated_cost_cents, estimated_hours_milli, risk, clean_notes,
                ),
            )
            opportunity_id = int(cursor.lastrowid)
        self.audit("opportunity_research_recorded", str(opportunity_id))
        return self.economic_opportunity(opportunity_id)

    def economic_opportunity(self, opportunity_id: int) -> dict[str, object]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id,created_at,title,source,estimated_revenue_cents,"
                "estimated_cost_cents,estimated_hours_milli,risk,notes,status,"
                "external_activity,action_authorized FROM economic_opportunities WHERE id=?",
                (opportunity_id,),
            ).fetchone()
        if row is None:
            raise ValueError("Opportunity was not found")
        result = dict(row)
        profit = int(result["estimated_revenue_cents"]) - int(result["estimated_cost_cents"])
        result["estimated_profit_cents"] = profit
        result["estimated_hourly_profit_cents"] = (
            profit * 1_000 // int(result["estimated_hours_milli"])
        )
        result["external_activity"] = bool(result["external_activity"])
        result["action_authorized"] = bool(result["action_authorized"])
        return result

    def recent_economic_opportunities(self, limit: int = 20) -> list[dict[str, object]]:
        with self._connect() as connection:
            ids = [
                int(row["id"])
                for row in connection.execute(
                    "SELECT id FROM economic_opportunities ORDER BY id DESC LIMIT ?", (limit,)
                ).fetchall()
            ]
        return [self.economic_opportunity(opportunity_id) for opportunity_id in ids]

    def record_deal_candidate(self, result: dict[str, object]) -> dict[str, object]:
        if (
            result.get("external_activity") is not False
            or result.get("action_authorized") is not False
            or result.get("purchase_authorized") is not False
            or result.get("capability_change") != "none"
            or result.get("actions_queued") != 0
            or result.get("actions_executed") != 0
            or result.get("heuristic_not_market_truth") is not True
        ):
            raise ValueError("Deal candidate attempts to create action or purchase authority")
        title = self._research_text(str(result.get("title", "")), label="Deal title", maximum=200)
        source_reference = self._research_text(
            str(result.get("source_reference", "")), label="Deal source", maximum=500
        )
        source_kind = self._research_text(
            str(result.get("source_kind", "")), label="Deal source kind", maximum=64
        )
        observed_at = self._research_text(
            str(result.get("observed_at", "")), label="Deal observation time", maximum=64
        )
        costs = result.get("costs")
        evidence = result.get("evidence")
        if not isinstance(costs, dict) or not isinstance(evidence, dict):
            raise ValueError("Deal candidate costs and evidence are required")
        if (
            evidence.get("external_action_authorized") is not False
            or evidence.get("capability_change") != "none"
        ):
            raise ValueError("Deal evidence cannot create external authority")
        total_cents = costs.get("total_acquisition_cents")
        if not isinstance(total_cents, int) or total_cents <= 0:
            raise ValueError("Deal candidate acquisition cost is invalid")
        evidence_status = evidence.get("decision")
        if evidence_status not in {"verified_for_analysis", "verification_required"}:
            raise ValueError("Deal candidate evidence status is invalid")
        recommendation = result.get("recommendation")
        if recommendation not in {
            "candidate_for_human_review", "watchlist", "low_priority",
            "verify_before_review", "high_risk_hold", "reject_incompatible",
        }:
            raise ValueError("Deal candidate recommendation is invalid")
        score = result.get("research_score")
        if not isinstance(score, (int, float)) or isinstance(score, bool) or not 0 <= score <= 100:
            raise ValueError("Deal candidate research score is invalid")
        score_milli = round(float(score) * 1_000)
        encoded = json.dumps(result, separators=(",", ":"), sort_keys=True)
        if len(encoded) > 100_000:
            raise ValueError("Deal candidate record exceeds the storage limit")
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO deal_candidates(created_at,title,source_reference,source_kind,"
                "observed_at,total_acquisition_cents,research_score_milli,evidence_status,"
                "recommendation,result_json) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    self._now(), title, source_reference, source_kind, observed_at,
                    total_cents, score_milli, evidence_status, recommendation, encoded,
                ),
            )
            candidate_id = int(cursor.lastrowid)
        self.audit("deal_candidate_scored", f"{candidate_id}: {recommendation}; no action")
        return self.deal_candidate(candidate_id)

    def deal_candidate(self, candidate_id: int) -> dict[str, object]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM deal_candidates WHERE candidate_id=?", (candidate_id,)
            ).fetchone()
        if row is None:
            raise ValueError("Deal candidate was not found")
        record = dict(row)
        record["result"] = json.loads(str(record.pop("result_json")))
        record["research_score"] = int(record.pop("research_score_milli")) / 1_000
        for key in ("external_activity", "action_authorized", "purchase_authorized"):
            record[key] = bool(record[key])
        return record

    def recent_deal_candidates(self, limit: int = 20) -> list[dict[str, object]]:
        if not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("Deal candidate limit must be 1 to 100")
        with self._connect() as connection:
            ids = [
                int(row["candidate_id"])
                for row in connection.execute(
                    "SELECT candidate_id FROM deal_candidates "
                    "ORDER BY candidate_id DESC LIMIT ?", (limit,)
                ).fetchall()
            ]
        return [self.deal_candidate(candidate_id) for candidate_id in ids]

    def record_deal_discovery(self, item: dict[str, object]) -> dict[str, object]:
        expected_keys = {
            "source_id", "external_item_id", "deduplication_key", "title", "item_url",
            "observed_at", "ask_price_cents", "shipping_cents", "shipping_known",
            "price_plus_shipping_cents", "tax_cents", "tax_known",
            "total_acquisition_cents", "condition", "condition_mapping_heuristic",
            "seller_risk", "seller_risk_heuristic", "seller_evidence", "buying_options",
            "hardware_profile_status", "scoring_ready", "evidence_status",
            "listing_text_untrusted", "external_activity", "network_requests",
            "action_authorized", "purchase_authorized", "actions_queued",
            "actions_executed", "capability_change",
        }
        if not isinstance(item, dict) or set(item) != expected_keys:
            raise ValueError("Deal discovery schema is invalid")
        if (
            item.get("source_id") != "ebay_browse_api"
            or item.get("hardware_profile_status") != "unresolved"
            or item.get("scoring_ready") is not False
            or item.get("evidence_status") != "unverified_adapter_input"
            or item.get("listing_text_untrusted") is not True
            or item.get("tax_known") is not False
            or item.get("tax_cents") is not None
            or item.get("total_acquisition_cents") is not None
            or item.get("external_activity") is not False
            or item.get("network_requests") != 0
            or item.get("action_authorized") is not False
            or item.get("purchase_authorized") is not False
            or item.get("actions_queued") != 0
            or item.get("actions_executed") != 0
            or item.get("capability_change") != "none"
        ):
            raise ValueError("Deal discovery attempts to bypass unresolved research limits")
        external_item_id = self._research_text(
            str(item["external_item_id"]), label="Discovery item ID", maximum=200
        )
        if item["deduplication_key"] != f"ebay:{external_item_id}":
            raise ValueError("Deal discovery deduplication key is invalid")
        title = self._research_text(str(item["title"]), label="Discovery title", maximum=200)
        item_url = self._research_text(
            str(item["item_url"]), label="Discovery item URL", maximum=1_000
        )
        parsed_url = urlparse(item_url)
        if (
            parsed_url.scheme != "https"
            or parsed_url.hostname not in {"www.ebay.com", "ebay.com"}
            or not parsed_url.path.startswith("/itm/")
            or parsed_url.username is not None
            or parsed_url.password is not None
        ):
            raise ValueError("Deal discovery item URL is invalid")
        observed_at = self._research_text(
            str(item["observed_at"]), label="Discovery observation time", maximum=64
        )
        try:
            observed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("Deal discovery observation time must be ISO 8601") from exc
        if observed.tzinfo is None:
            raise ValueError("Deal discovery observation time must include a timezone")
        ask_price_cents = item["ask_price_cents"]
        shipping_cents = item["shipping_cents"]
        shipping_known = item["shipping_known"]
        if type(ask_price_cents) is not int or ask_price_cents <= 0:
            raise ValueError("Deal discovery ask price is invalid")
        if type(shipping_known) is not bool or (
            shipping_known and (type(shipping_cents) is not int or shipping_cents < 0)
        ) or (not shipping_known and shipping_cents is not None):
            raise ValueError("Deal discovery shipping state is invalid")
        expected_price_plus_shipping = (
            ask_price_cents + shipping_cents if shipping_known else None
        )
        if item["price_plus_shipping_cents"] != expected_price_plus_shipping:
            raise ValueError("Deal discovery partial cost is inconsistent")
        if item["condition"] not in {"new", "used_good", "used_unknown", "parts_only"}:
            raise ValueError("Deal discovery condition is invalid")
        if item["seller_risk"] not in {"low", "medium", "high"}:
            raise ValueError("Deal discovery seller risk is invalid")
        if item["condition_mapping_heuristic"] is not True or item["seller_risk_heuristic"] is not True:
            raise ValueError("Deal discovery heuristics must remain explicitly labeled")
        if not isinstance(item["seller_evidence"], dict) or not isinstance(item["buying_options"], list):
            raise ValueError("Deal discovery evidence fields are invalid")
        if not all(isinstance(option, str) and len(option) <= 100 for option in item["buying_options"]):
            raise ValueError("Deal discovery buying options are invalid")
        encoded = json.dumps(item, separators=(",", ":"), sort_keys=True)
        if len(encoded) > 20_000:
            raise ValueError("Deal discovery record exceeds the storage limit")

        with self._connect() as connection:
            existing = connection.execute(
                "SELECT discovery_id,last_seen_at FROM deal_discoveries "
                "WHERE source_id=? AND external_item_id=?",
                ("ebay_browse_api", external_item_id),
            ).fetchone()
            if existing is None:
                cursor = connection.execute(
                    "INSERT INTO deal_discoveries(source_id,external_item_id,"
                    "deduplication_key,first_seen_at,last_seen_at,title,item_url,"
                    "ask_price_cents,shipping_cents,shipping_known,condition,seller_risk,"
                    "evidence_status,normalized_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        "ebay_browse_api", external_item_id, item["deduplication_key"],
                        observed_at, observed_at, title, item_url, ask_price_cents,
                        shipping_cents, int(shipping_known), item["condition"],
                        item["seller_risk"], item["evidence_status"], encoded,
                    ),
                )
                discovery_id = int(cursor.lastrowid)
                was_new = True
            else:
                discovery_id = int(existing["discovery_id"])
                existing_seen = datetime.fromisoformat(
                    str(existing["last_seen_at"]).replace("Z", "+00:00")
                )
                if observed >= existing_seen:
                    connection.execute(
                        "UPDATE deal_discoveries SET last_seen_at=?,observation_count="
                        "observation_count+1,title=?,item_url=?,ask_price_cents=?,"
                        "shipping_cents=?,shipping_known=?,condition=?,seller_risk=?,"
                        "normalized_json=? WHERE discovery_id=?",
                        (
                            observed_at, title, item_url, ask_price_cents, shipping_cents,
                            int(shipping_known), item["condition"], item["seller_risk"],
                            encoded, discovery_id,
                        ),
                    )
                else:
                    connection.execute(
                        "UPDATE deal_discoveries SET observation_count=observation_count+1 "
                        "WHERE discovery_id=?", (discovery_id,)
                    )
                was_new = False
        self.audit(
            "deal_discovery_recorded" if was_new else "deal_discovery_refreshed",
            f"{discovery_id}: unresolved; no scoring or action",
        )
        return {**self.deal_discovery(discovery_id), "was_new": was_new}

    def deal_discovery(self, discovery_id: int) -> dict[str, object]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM deal_discoveries WHERE discovery_id=?", (discovery_id,)
            ).fetchone()
        if row is None:
            raise ValueError("Deal discovery was not found")
        record = dict(row)
        record["normalized"] = json.loads(str(record.pop("normalized_json")))
        for key in (
            "shipping_known", "tax_known", "scoring_ready", "external_activity",
            "action_authorized", "purchase_authorized",
        ):
            record[key] = bool(record[key])
        return record

    def recent_deal_discoveries(self, limit: int = 20) -> list[dict[str, object]]:
        if not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("Deal discovery limit must be 1 to 100")
        with self._connect() as connection:
            ids = [
                int(row["discovery_id"])
                for row in connection.execute(
                    "SELECT discovery_id FROM deal_discoveries "
                    "ORDER BY last_seen_at DESC,discovery_id DESC LIMIT ?", (limit,)
                ).fetchall()
            ]
        return [self.deal_discovery(discovery_id) for discovery_id in ids]

    @staticmethod
    def _prayer_text(
        value: object, *, label: str, maximum: int, allow_empty: bool = False
    ) -> str:
        if not isinstance(value, str):
            raise ValueError(f"{label} must be text")
        clean = value.strip()
        if not clean and not allow_empty:
            raise ValueError(f"{label} is required")
        if len(clean) > maximum:
            raise ValueError(f"{label} exceeds the {maximum}-character limit")
        return clean

    @staticmethod
    def _prayer_timestamp(value: object, *, label: str, allow_empty: bool = False) -> str | None:
        if value is None or (isinstance(value, str) and not value.strip()):
            if allow_empty:
                return None
            raise ValueError(f"{label} is required")
        if not isinstance(value, str) or len(value) > 64:
            raise ValueError(f"{label} must be a bounded ISO 8601 timestamp")
        clean = value.strip()
        try:
            parsed = datetime.fromisoformat(clean.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"{label} must be ISO 8601") from exc
        if parsed.tzinfo is None:
            raise ValueError(f"{label} must include a timezone")
        return clean

    @staticmethod
    def _prayer_fingerprint(text: str) -> str:
        normalized = " ".join(re.findall(r"[a-z0-9]+", text.casefold()))
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    @staticmethod
    def _prayer_record_digest(record: dict[str, object]) -> str:
        fields = (
            "source_context", "source_reference", "received_at", "requester_display",
            "identity_handling", "request_text", "sharing_scope", "consent_notes",
            "status", "follow_up_at", "private_notes", "sensitivity",
            "provenance_status", "confidence", "redacted",
        )
        encoded = json.dumps(
            {field: record.get(field) for field in fields},
            separators=(",", ":"), sort_keys=True,
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def prayer_duplicate_suggestions(
        self, request_text: str, *, exclude_prayer_id: int | None = None, limit: int = 5
    ) -> list[dict[str, object]]:
        clean_text = self._prayer_text(
            request_text, label="Prayer request", maximum=4_000
        )
        if type(limit) is not int or not 1 <= limit <= 20:
            raise ValueError("Prayer duplicate limit must be 1 to 20")
        fingerprint = self._prayer_fingerprint(clean_text)
        tokens = set(re.findall(r"[a-z0-9]+", clean_text.casefold()))
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT prayer_id,request_text,fingerprint_sha256,status,requester_display "
                "FROM prayer_requests WHERE redacted=0 AND status!='archived' "
                "ORDER BY prayer_id DESC LIMIT 200"
            ).fetchall()
        suggestions: list[dict[str, object]] = []
        for row in rows:
            prayer_id = int(row["prayer_id"])
            if exclude_prayer_id is not None and prayer_id == exclude_prayer_id:
                continue
            candidate_tokens = set(
                re.findall(r"[a-z0-9]+", str(row["request_text"]).casefold())
            )
            exact = str(row["fingerprint_sha256"]) == fingerprint
            union = tokens | candidate_tokens
            similarity = len(tokens & candidate_tokens) / len(union) if union else 0.0
            if exact or (min(len(tokens), len(candidate_tokens)) >= 4 and similarity >= 0.72):
                suggestions.append({
                    "prayer_id": prayer_id,
                    "match": "exact" if exact else "possible",
                    "similarity": round(1.0 if exact else similarity, 3),
                    "status": str(row["status"]),
                    "requester_display": str(row["requester_display"]),
                    "human_review_required": True,
                    "automatically_merged": False,
                })
        suggestions.sort(key=lambda item: (-float(item["similarity"]), -int(item["prayer_id"])))
        return suggestions[:limit]

    def record_prayer_request(
        self,
        *,
        source_context: str,
        request_text: str,
        received_at: str | None = None,
        requester_display: str = "",
        identity_handling: str = "omitted",
        source_reference: str = "",
        sharing_scope: str = "private_dustin",
        consent_notes: str = "",
        status: str = "active",
        follow_up_at: str | None = None,
        private_notes: str = "",
        sensitivity: str = "sensitive",
        provenance_status: str = "user_supplied",
        confidence: str = "high",
    ) -> dict[str, object]:
        allowed_sources = {
            "direct_to_dustin", "slack_prayer_team", "google_messages_giant_killers",
            "whatsapp_sunday", "other_private",
        }
        if source_context not in allowed_sources:
            raise ValueError("Prayer source context is invalid")
        if identity_handling not in {"omitted", "initials", "first_name", "full_name_explicit"}:
            raise ValueError("Prayer identity handling is invalid")
        if sharing_scope not in {"private_dustin", "source_group_only", "explicitly_shareable"}:
            raise ValueError("Prayer sharing scope is invalid")
        if status not in {"active", "follow_up", "answered", "archived"}:
            raise ValueError("Prayer status is invalid")
        if sensitivity not in {"standard", "sensitive", "highly_sensitive"}:
            raise ValueError("Prayer sensitivity is invalid")
        if provenance_status not in {
            "user_supplied", "direct_copy_unverified", "clarified_by_dustin"
        }:
            raise ValueError("Prayer provenance status is invalid")
        if confidence not in {"low", "medium", "high"}:
            raise ValueError("Prayer confidence is invalid")
        clean_request = self._prayer_text(
            request_text, label="Prayer request", maximum=4_000
        )
        clean_requester = self._prayer_text(
            requester_display, label="Requester display", maximum=200, allow_empty=True
        )
        if identity_handling == "omitted" and clean_requester:
            raise ValueError("Requester display must be empty when identity handling is omitted")
        clean_reference = self._prayer_text(
            source_reference, label="Source reference", maximum=500, allow_empty=True
        )
        clean_consent = self._prayer_text(
            consent_notes, label="Consent notes", maximum=1_000, allow_empty=True
        )
        clean_notes = self._prayer_text(
            private_notes, label="Private notes", maximum=2_000, allow_empty=True
        )
        clean_received = self._prayer_timestamp(
            received_at or self._now(), label="Received at"
        )
        clean_follow_up = self._prayer_timestamp(
            follow_up_at, label="Follow-up at", allow_empty=True
        )
        now = self._now()
        fingerprint = self._prayer_fingerprint(clean_request)
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO prayer_requests(created_at,updated_at,last_reviewed_at,"
                "source_context,source_reference,received_at,requester_display,"
                "identity_handling,request_text,fingerprint_sha256,sharing_scope,"
                "consent_notes,status,follow_up_at,private_notes,sensitivity,"
                "provenance_status,confidence) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    now, now, now, source_context, clean_reference, clean_received,
                    clean_requester, identity_handling, clean_request, fingerprint,
                    sharing_scope, clean_consent, status, clean_follow_up, clean_notes,
                    sensitivity, provenance_status, confidence,
                ),
            )
            prayer_id = int(cursor.lastrowid)
            new_record = dict(connection.execute(
                "SELECT * FROM prayer_requests WHERE prayer_id=?", (prayer_id,)
            ).fetchone())
            connection.execute(
                "INSERT INTO prayer_request_changes(prayer_id,changed_at,change_type,"
                "reason,previous_digest,new_digest,status_before,status_after) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    prayer_id, now, "created", "Manual local entry", None,
                    self._prayer_record_digest(new_record), None, status,
                ),
            )
        self.audit("prayer_request_recorded", f"{prayer_id}: {status}; local only")
        result = self.prayer_request(prayer_id)
        result["duplicate_suggestions"] = self.prayer_duplicate_suggestions(
            clean_request, exclude_prayer_id=prayer_id
        )
        return result

    def prayer_request(self, prayer_id: int) -> dict[str, object]:
        if type(prayer_id) is not int or prayer_id < 1:
            raise ValueError("Prayer request ID is invalid")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM prayer_requests WHERE prayer_id=?", (prayer_id,)
            ).fetchone()
        if row is None:
            raise ValueError("Prayer request was not found")
        record = dict(row)
        for field in (
            "redacted", "external_content_untrusted", "cloud_processing_authorized",
            "cross_post_authorized", "messages_sent", "action_authorized",
        ):
            record[field] = bool(record[field])
        record["external_activity"] = False
        return record

    def recent_prayer_requests(
        self, limit: int = 50, *, include_archived: bool = True
    ) -> list[dict[str, object]]:
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError("Prayer request limit must be 1 to 200")
        where = "" if include_archived else "WHERE status!='archived'"
        with self._connect() as connection:
            ids = [
                int(row["prayer_id"])
                for row in connection.execute(
                    f"SELECT prayer_id FROM prayer_requests {where} "
                    "ORDER BY prayer_id DESC LIMIT ?", (limit,)
                ).fetchall()
            ]
        return [self.prayer_request(prayer_id) for prayer_id in ids]

    def update_prayer_status(
        self, prayer_id: int, *, status: str, reason: str, follow_up_at: str | None = None
    ) -> dict[str, object]:
        if status not in {"active", "follow_up", "answered", "archived"}:
            raise ValueError("Prayer status is invalid")
        clean_reason = self._prayer_text(reason, label="Status reason", maximum=500)
        clean_follow_up = self._prayer_timestamp(
            follow_up_at, label="Follow-up at", allow_empty=True
        )
        before = self.prayer_request(prayer_id)
        if before["redacted"]:
            raise ValueError("A redacted prayer request cannot change status")
        now = self._now()
        with self._connect() as connection:
            connection.execute(
                "UPDATE prayer_requests SET status=?,follow_up_at=?,updated_at=?,"
                "last_reviewed_at=? WHERE prayer_id=?",
                (status, clean_follow_up, now, now, prayer_id),
            )
        after = self.prayer_request(prayer_id)
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO prayer_request_changes(prayer_id,changed_at,change_type,"
                "reason,previous_digest,new_digest,status_before,status_after) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    prayer_id, now, "status_changed", clean_reason,
                    self._prayer_record_digest(before), self._prayer_record_digest(after),
                    str(before["status"]), status,
                ),
            )
        self.audit("prayer_status_changed", f"{prayer_id}: {before['status']} -> {status}")
        return after

    def correct_prayer_request(
        self,
        prayer_id: int,
        *,
        request_text: str,
        requester_display: str,
        identity_handling: str,
        source_reference: str,
        sharing_scope: str,
        consent_notes: str,
        follow_up_at: str | None,
        private_notes: str,
        sensitivity: str,
        provenance_status: str,
        confidence: str,
        reason: str,
    ) -> dict[str, object]:
        before = self.prayer_request(prayer_id)
        if before["redacted"]:
            raise ValueError("A redacted prayer request cannot be corrected")
        clean_reason = self._prayer_text(reason, label="Correction reason", maximum=500)
        clean_request = self._prayer_text(request_text, label="Prayer request", maximum=4_000)
        clean_requester = self._prayer_text(
            requester_display, label="Requester display", maximum=200, allow_empty=True
        )
        if identity_handling not in {"omitted", "initials", "first_name", "full_name_explicit"}:
            raise ValueError("Prayer identity handling is invalid")
        if identity_handling == "omitted" and clean_requester:
            raise ValueError("Requester display must be empty when identity handling is omitted")
        if sharing_scope not in {"private_dustin", "source_group_only", "explicitly_shareable"}:
            raise ValueError("Prayer sharing scope is invalid")
        if sensitivity not in {"standard", "sensitive", "highly_sensitive"}:
            raise ValueError("Prayer sensitivity is invalid")
        if provenance_status not in {
            "user_supplied", "direct_copy_unverified", "clarified_by_dustin"
        }:
            raise ValueError("Prayer provenance status is invalid")
        if confidence not in {"low", "medium", "high"}:
            raise ValueError("Prayer confidence is invalid")
        clean_reference = self._prayer_text(
            source_reference, label="Source reference", maximum=500, allow_empty=True
        )
        clean_consent = self._prayer_text(
            consent_notes, label="Consent notes", maximum=1_000, allow_empty=True
        )
        clean_notes = self._prayer_text(
            private_notes, label="Private notes", maximum=2_000, allow_empty=True
        )
        clean_follow_up = self._prayer_timestamp(
            follow_up_at, label="Follow-up at", allow_empty=True
        )
        now = self._now()
        with self._connect() as connection:
            connection.execute(
                "UPDATE prayer_requests SET request_text=?,requester_display=?,"
                "identity_handling=?,source_reference=?,sharing_scope=?,consent_notes=?,"
                "follow_up_at=?,private_notes=?,sensitivity=?,provenance_status=?,"
                "confidence=?,fingerprint_sha256=?,updated_at=?,last_reviewed_at=? "
                "WHERE prayer_id=?",
                (
                    clean_request, clean_requester, identity_handling, clean_reference,
                    sharing_scope, clean_consent, clean_follow_up, clean_notes,
                    sensitivity, provenance_status, confidence,
                    self._prayer_fingerprint(clean_request), now, now, prayer_id,
                ),
            )
        after = self.prayer_request(prayer_id)
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO prayer_request_changes(prayer_id,changed_at,change_type,"
                "reason,previous_digest,new_digest,status_before,status_after) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    prayer_id, now, "corrected", clean_reason,
                    self._prayer_record_digest(before), self._prayer_record_digest(after),
                    str(before["status"]), str(after["status"]),
                ),
            )
        self.audit("prayer_request_corrected", f"{prayer_id}: sensitive text omitted")
        result = after
        result["duplicate_suggestions"] = self.prayer_duplicate_suggestions(
            clean_request, exclude_prayer_id=prayer_id
        )
        return result

    def redact_prayer_request(
        self, prayer_id: int, *, confirmation: str, reason: str
    ) -> dict[str, object]:
        if confirmation != f"REDACT PRAYER {prayer_id}":
            raise ValueError(f"Confirmation must be exactly: REDACT PRAYER {prayer_id}")
        clean_reason = self._prayer_text(reason, label="Redaction reason", maximum=500)
        before = self.prayer_request(prayer_id)
        if before["redacted"]:
            return before
        now = self._now()
        with self._connect() as connection:
            connection.execute(
                "UPDATE prayer_requests SET updated_at=?,last_reviewed_at=?,"
                "source_reference='',requester_display='',identity_handling='omitted',"
                "request_text='[redacted]',fingerprint_sha256=?,"
                "sharing_scope='private_dustin',consent_notes='',status='archived',"
                "follow_up_at=NULL,private_notes='',redacted=1 WHERE prayer_id=?",
                (now, now, self._prayer_fingerprint("[redacted]"), prayer_id),
            )
        after = self.prayer_request(prayer_id)
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO prayer_request_changes(prayer_id,changed_at,change_type,"
                "reason,previous_digest,new_digest,status_before,status_after) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    prayer_id, now, "redacted", clean_reason,
                    self._prayer_record_digest(before), self._prayer_record_digest(after),
                    str(before["status"]), "archived",
                ),
            )
        self.audit("prayer_request_redacted", f"{prayer_id}: plaintext removed from live database")
        return after

    def prayer_request_changes(self, prayer_id: int) -> list[dict[str, object]]:
        self.prayer_request(prayer_id)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM prayer_request_changes WHERE prayer_id=? "
                "ORDER BY change_id", (prayer_id,)
            ).fetchall()
        return [dict(row) for row in rows]

    def link_prayer_requests(
        self,
        from_prayer_id: int,
        to_prayer_id: int,
        *,
        relation_type: str,
        reason: str,
        confirmation: str,
    ) -> dict[str, object]:
        if confirmation != "CONFIRM PRAYER LINK":
            raise ValueError("Confirmation must be exactly: CONFIRM PRAYER LINK")
        if from_prayer_id == to_prayer_id:
            raise ValueError("A prayer request cannot link to itself")
        if relation_type not in {"possible_duplicate", "related", "supersedes"}:
            raise ValueError("Prayer relation type is invalid")
        self.prayer_request(from_prayer_id)
        self.prayer_request(to_prayer_id)
        clean_reason = self._prayer_text(reason, label="Link reason", maximum=500)
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO prayer_request_links(created_at,from_prayer_id,to_prayer_id,"
                "relation_type,reason,confirmed_by) VALUES (?,?,?,?,?,?)",
                (
                    self._now(), from_prayer_id, to_prayer_id, relation_type,
                    clean_reason, "dustin",
                ),
            )
            link_id = int(cursor.lastrowid)
            row = connection.execute(
                "SELECT * FROM prayer_request_links WHERE link_id=?", (link_id,)
            ).fetchone()
        self.audit("prayer_requests_linked", f"{from_prayer_id} -> {to_prayer_id}: {relation_type}")
        return dict(row)

    def prayer_summary(
        self, *, source_connections: dict[str, bool] | None = None
    ) -> dict[str, object]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT status,COUNT(*) total FROM prayer_requests GROUP BY status"
            ).fetchall()
            redacted = int(connection.execute(
                "SELECT COUNT(*) FROM prayer_requests WHERE redacted=1"
            ).fetchone()[0])
            links = int(connection.execute(
                "SELECT COUNT(*) FROM prayer_request_links"
            ).fetchone()[0])
        counts = {status: 0 for status in ("active", "follow_up", "answered", "archived")}
        counts.update({str(row["status"]): int(row["total"]) for row in rows})
        connections = {
            "slack_prayer_team": False,
            "google_messages_giant_killers": False,
            "whatsapp_sunday": False,
        }
        if source_connections is not None:
            if set(source_connections) != set(connections) or any(
                type(value) is not bool for value in source_connections.values()
            ):
                raise ValueError("Prayer source connection status is invalid")
            connections.update(source_connections)
        connected = all(connections.values())
        return {
            "status": "working_local_selected_capture" if connected else "working_local_only",
            "requests_total": sum(counts.values()),
            "requests_by_status": counts,
            "redacted_total": redacted,
            "confirmed_links": links,
            "entry_method": "manual_or_user_selected_capture" if connected else "manual_only",
            "source_connections": connections,
            "cloud_processing_authorized": False,
            "cross_post_authorized": False,
            "messages_sent": 0,
            "external_activity": False,
            "actions_queued": 0,
            "actions_executed": 0,
            "capability_change": "none",
        }

    def record_hardware_target(
        self,
        *,
        component: str,
        target_price_cents: int,
        expected_capability: str,
        compatibility_status: str,
        notes: str,
    ) -> dict[str, object]:
        clean_component = self._research_text(component, label="Component", maximum=200)
        clean_capability = self._research_text(
            expected_capability, label="Expected capability", maximum=1_000
        )
        clean_notes = self._research_text(notes, label="Notes", maximum=2_000)
        if type(target_price_cents) is not int or target_price_cents < 0:
            raise ValueError("Target price must be non-negative cents")
        if compatibility_status not in {
            "unknown", "needs_review", "compatible", "incompatible"
        }:
            raise ValueError("Compatibility status is invalid")
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO hardware_targets("
                "created_at,component,target_price_cents,expected_capability,"
                "compatibility_status,notes) VALUES (?,?,?,?,?,?)",
                (
                    self._now(), clean_component, target_price_cents,
                    clean_capability, compatibility_status, clean_notes,
                ),
            )
            target_id = int(cursor.lastrowid)
        self.audit("hardware_target_recorded", str(target_id))
        return self.hardware_target(target_id)

    def hardware_target(self, target_id: int) -> dict[str, object]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id,created_at,component,target_price_cents,expected_capability,"
                "compatibility_status,notes,status,purchase_authorized "
                "FROM hardware_targets WHERE id=?",
                (target_id,),
            ).fetchone()
        if row is None:
            raise ValueError("Hardware target was not found")
        result = dict(row)
        result["purchase_authorized"] = bool(result["purchase_authorized"])
        return result

    def recent_hardware_targets(self, limit: int = 20) -> list[dict[str, object]]:
        with self._connect() as connection:
            ids = [
                int(row["id"])
                for row in connection.execute(
                    "SELECT id FROM hardware_targets ORDER BY id DESC LIMIT ?", (limit,)
                ).fetchall()
            ]
        return [self.hardware_target(target_id) for target_id in ids]

    def research_summary(self) -> dict[str, object]:
        with self._connect() as connection:
            opportunity_count = int(
                connection.execute("SELECT COUNT(*) FROM economic_opportunities").fetchone()[0]
            )
            hardware_count = int(
                connection.execute("SELECT COUNT(*) FROM hardware_targets").fetchone()[0]
            )
            deal_candidate_count = int(
                connection.execute("SELECT COUNT(*) FROM deal_candidates").fetchone()[0]
            )
            deal_discovery_count = int(
                connection.execute("SELECT COUNT(*) FROM deal_discoveries").fetchone()[0]
            )
        return {
            "opportunity_count": opportunity_count,
            "hardware_target_count": hardware_count,
            "deal_candidate_count": deal_candidate_count,
            "deal_discovery_count": deal_discovery_count,
            "opportunities": self.recent_economic_opportunities(),
            "hardware_targets": self.recent_hardware_targets(),
            "deal_candidates": self.recent_deal_candidates(),
            "deal_discoveries": self.recent_deal_discoveries(),
            "external_activity": False,
            "transactions_executed": 0,
            "purchases_executed": 0,
            "contracts_accepted": 0,
        }

    def record_provenance(self, *, source: str, statement: str) -> int:
        clean_source = source.strip()
        clean_statement = statement.strip()
        if not clean_source or len(clean_source) > 100:
            raise ValueError("Source must be between 1 and 100 characters")
        if not clean_statement or len(clean_statement) > 2000:
            raise ValueError("Statement must be between 1 and 2000 characters")
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO provenance_records(created_at,source,statement) VALUES (?,?,?)",
                (self._now(), clean_source, clean_statement),
            )
            record_id = int(cursor.lastrowid)
        self.audit("provenance_recorded", f"{record_id}: {clean_source}")
        return record_id

    def provenance_records(self, status: str | None = None) -> list[tuple[int, str, str, str]]:
        if status is not None and status not in {"unverified", "confirmed", "rejected"}:
            raise ValueError("Invalid provenance status")
        query = "SELECT id,source,statement,status FROM provenance_records"
        parameters: tuple[str, ...] = ()
        if status is not None:
            query += " WHERE status=?"
            parameters = (status,)
        query += " ORDER BY id"
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [(int(row["id"]), row["source"], row["statement"], row["status"]) for row in rows]

    def decide_provenance(self, record_id: int, decision: str) -> bool:
        if decision not in {"confirmed", "rejected"}:
            raise ValueError("Decision must be confirmed or rejected")
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE provenance_records SET status=? WHERE id=? AND status='unverified'",
                (decision, record_id),
            )
            changed = cursor.rowcount == 1
        if changed:
            self.audit(f"provenance_{decision}", str(record_id))
        return changed

    def enqueue_job(self, handler: str, payload_json: str = "{}", max_attempts: int = 2) -> int:
        if max_attempts < 1 or max_attempts > 3:
            raise ValueError("Job attempts must be between 1 and 3")
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO jobs(created_at,handler,payload_json,max_attempts) VALUES (?,?,?,?)",
                (self._now(), handler, payload_json, max_attempts),
            )
            job_id = int(cursor.lastrowid)
        self.audit("job_queued", f"{job_id}: {handler}")
        return job_id

    def claim_next_job(self) -> dict[str, object] | None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT id,handler,payload_json,attempts,max_attempts FROM jobs "
                "WHERE status='pending' ORDER BY id LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                "UPDATE jobs SET status='running',attempts=attempts+1 WHERE id=?",
                (row["id"],),
            )
        return {
            "id": int(row["id"]), "handler": row["handler"],
            "payload_json": row["payload_json"], "attempts": int(row["attempts"]) + 1,
            "max_attempts": int(row["max_attempts"]),
        }

    def finish_job(self, job_id: int, result_json: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE jobs SET status='succeeded',result_json=?,last_error=NULL "
                "WHERE id=? AND status='running'", (result_json, job_id),
            )
        self.audit("job_succeeded", str(job_id))

    def fail_job(self, job_id: int, error: str) -> str:
        bounded_error = error[:1000]
        with self._connect() as connection:
            row = connection.execute(
                "SELECT attempts,max_attempts FROM jobs WHERE id=? AND status='running'", (job_id,)
            ).fetchone()
            if row is None:
                raise ValueError("Running job was not found")
            retry = int(row["attempts"]) < int(row["max_attempts"])
            status = "pending" if retry else "review_required"
            connection.execute(
                "UPDATE jobs SET status=?,last_error=? WHERE id=?", (status, bounded_error, job_id)
            )
            if not retry:
                connection.execute(
                    "INSERT INTO repair_proposals(created_at,job_id,failure,proposal) VALUES (?,?,?,?)",
                    (
                        self._now(), job_id, bounded_error,
                        "Inspect the structured failure and propose a tracked code/config change. "
                        "Do not execute generated code automatically.",
                    ),
                )
        self.audit("job_retry" if retry else "job_review_required", str(job_id))
        return status

    def job_summary(self) -> dict[str, int]:
        with self._connect() as connection:
            rows = connection.execute("SELECT status,COUNT(*) total FROM jobs GROUP BY status").fetchall()
        result = {status: 0 for status in ("pending", "running", "succeeded", "failed", "review_required")}
        result.update({row["status"]: int(row["total"]) for row in rows})
        return result

    def recent_jobs(self, limit: int = 20) -> list[tuple[int, str, str, int, int]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id,handler,status,attempts,max_attempts FROM jobs ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            (int(row["id"]), row["handler"], row["status"], int(row["attempts"]), int(row["max_attempts"]))
            for row in rows
        ]
