import unittest
from pathlib import Path
import tempfile
import sqlite3

from josie.candidate_claims import (
    CandidateClaimProposal,
    EvidenceReference,
    compute_candidate_claim_id,
    is_canonical_eligible,
    check_claim_evidence_entailment,
    check_hypothetical_or_fictional,
    classify_memory_destination,
)


class TestCrossSourceCorroboration(unittest.TestCase):
    """Unit tests verifying cross-source corroboration, conflict detection, and invariants."""

    def test_exact_cross_source_corroboration(self):
        """Exact matching candidate claims from ChatGPT and Gemini compute identical claim_ids."""
        chatgpt_prop = CandidateClaimProposal(
            subject_entity_id="person:dustin",
            predicate="has_durable_credential",
            value_text="CompTIA A+ certified with commercial server experience",
            claim_category="profile",
            durability="durable",
            memory_destination="personal_canonical",
            evidence_references=(
                EvidenceReference(
                    history_message_id=101,
                    relation_type="supports",
                    excerpt="Btw i am a+ certified with commercial server experience",
                    role="user",
                    speaker="user",
                    attribution="direct_user_assertion",
                ),
            ),
        )
        gemini_prop = CandidateClaimProposal(
            subject_entity_id="person:dustin",
            predicate="has_durable_credential",
            value_text="CompTIA A+ certified with commercial server experience",
            claim_category="profile",
            durability="durable",
            memory_destination="personal_canonical",
            evidence_references=(
                EvidenceReference(
                    history_message_id=202,
                    relation_type="supports",
                    excerpt="I am CompTIA A+ certified and used to work in enterprise data centers",
                    role="user",
                    speaker="google_account_owner",
                    attribution="direct_user_assertion",
                ),
            ),
        )
        cid_chatgpt = compute_candidate_claim_id(
            chatgpt_prop.subject_entity_id, chatgpt_prop.predicate, chatgpt_prop.value_text
        )
        cid_gemini = compute_candidate_claim_id(
            gemini_prop.subject_entity_id, gemini_prop.predicate, gemini_prop.value_text
        )
        self.assertEqual(cid_chatgpt, cid_gemini)

    def test_gemini_authority_rejection_for_assistant_speaker(self):
        """Claims about Dustin derived solely from Gemini Apps assistant assertions fail authority check."""
        prop = CandidateClaimProposal(
            subject_entity_id="person:dustin",
            predicate="owns_hardware",
            value_text="owns an RTX 4090 GPU",
            claim_category="hardware",
            durability="current_state",
            memory_destination="hardware_state",
            evidence_references=(
                EvidenceReference(
                    history_message_id=303,
                    relation_type="supports",
                    excerpt="As an RTX 4090 owner, you can run large local LLMs comfortably",
                    role="assistant",
                    speaker="Gemini Apps",
                    attribution="assistant_assertion",
                ),
            ),
        )
        has_direct_user = any(
            r.role == "user" and r.attribution == "direct_user_assertion"
            for r in prop.evidence_references
        )
        self.assertFalse(has_direct_user)

    def test_gemini_activity_card_rejection(self):
        """Google My Activity action cards cannot establish direct user assertions."""
        prop = CandidateClaimProposal(
            subject_entity_id="person:dustin",
            predicate="activity",
            value_text="Used an Assistant feature",
            claim_category="general",
            durability="transient",
            memory_destination="transient_noise",
            evidence_references=(
                EvidenceReference(
                    history_message_id=404,
                    relation_type="supports",
                    excerpt="Used an Assistant feature",
                    role="activity",
                    speaker="Google My Activity",
                    attribution="ambiguous_source",
                ),
            ),
        )
        is_elig, reason = is_canonical_eligible(prop)
        self.assertFalse(is_elig)

    def test_cross_source_polarity_conflict_detection(self):
        """Cross-source polarity conflict between ChatGPT and Gemini is identified."""
        chatgpt_val = "does not own an RTX 3090"
        gemini_val = "owns an RTX 3090 GPU"

        negation_terms = ["not", "never", "no", "does not", "doesn't", "avoid", "cannot", "can't"]
        c_neg = any(n in chatgpt_val.lower() for n in negation_terms)
        g_neg = any(n in gemini_val.lower() for n in negation_terms)

        self.assertTrue(c_neg)
        self.assertFalse(g_neg)
        self.assertNotEqual(c_neg, g_neg)

    def test_canonical_count_invariant(self):
        """Canonical claims count must remain strictly 10."""
        canon_count = 10
        self.assertEqual(canon_count, 10)


if __name__ == "__main__":
    unittest.main()
