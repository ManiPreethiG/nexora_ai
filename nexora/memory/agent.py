"""Memory Agent for Nexora AI.

Responsible for retrieving and storing relevant historical knowledge,
coordinating pre-audit recall, retaining meaningful post-audit knowledge in Hindsight,
and maintaining durable longitudinal history for each website.
"""

import os
import json
import logging
import datetime as dt
from typing import Dict, List, Any, Optional

from nexora.identity import WebsiteIdentity
from nexora.models import AuditSnapshot, ImplementationEvent, AuditComparison
from nexora.memory.hindsight_client import HindsightMemoryClient

logger = logging.getLogger("nexora.memory_agent")


class MemoryAgent:
    """Specialized agent governing persistent memory operations for Nexora AI."""

    def __init__(self, hindsight_client: Optional[HindsightMemoryClient] = None):
        self.client = hindsight_client or HindsightMemoryClient()

    def recall_history(self, identity: WebsiteIdentity) -> Dict[str, Any]:
        """Recall relevant historical audit context for the website identity.
        
        Returns:
            dict containing:
              - 'is_first_audit': bool
              - 'audit_count': int
              - 'snapshots': List[AuditSnapshot]
              - 'events': List[ImplementationEvent]
              - 'hindsight_memories': List[Dict]
              - 'latest_snapshot': Optional[AuditSnapshot]
        """
        bank_id = identity.bank_id

        # 1. Retrieve raw recall items from Hindsight if available
        hindsight_memories = self.client.recall(
            bank_id=bank_id,
            query=f"Audit history, previous findings, fixes, and recommendations for {identity.domain}",
            tags=["audit_summary", "outcome", "user_action"],
        )

        # 2. Retrieve chronological audit snapshots from durable store
        raw_snapshots = self.client.load_local_snapshots(bank_id)
        snapshots = [AuditSnapshot.from_dict(s) for s in raw_snapshots]

        # 3. Retrieve user action events
        raw_events = self.client.load_local_events(bank_id)
        events = [ImplementationEvent.from_dict(e) for e in raw_events]

        is_first_audit = len(snapshots) == 0
        latest_snapshot = snapshots[-1] if snapshots else None

        return {
            "is_first_audit": is_first_audit,
            "audit_count": len(snapshots),
            "snapshots": snapshots,
            "events": events,
            "hindsight_memories": hindsight_memories,
            "latest_snapshot": latest_snapshot,
            "hindsight_live": self.client.is_live,
        }

    def retain_audit(
        self,
        identity: WebsiteIdentity,
        snapshot: AuditSnapshot,
        comparison: AuditComparison,
    ) -> bool:
        """Store durable audit summary, comparison results, and learned outcomes in Hindsight."""
        bank_id = identity.bank_id

        # 1. Persist local structured snapshot for deterministic comparison
        self.client.save_local_snapshot(bank_id, snapshot.to_dict())

        # 2. Synthesize durable knowledge (concise, factual, non-causal)
        summary_lines = [
            f"Website Audit #{comparison.audit_number} for {identity.domain} on {snapshot.audited_at}.",
            f"Overall AI Discoverability Score: {snapshot.overall_scores.get('ai_discoverability_score', 0)}/100.",
            f"On-site Engagement Score: {snapshot.overall_scores.get('on_site_engagement_score', 0)}/100.",
            f"Total findings: {snapshot.total_findings} (Critical: {snapshot.severity_counts.get('critical', 0)}, "
            f"High: {snapshot.severity_counts.get('high', 0)}, Medium: {snapshot.severity_counts.get('medium', 0)}).",
        ]

        if not comparison.is_first_audit:
            score_delta = comparison.score_changes.get("ai_discoverability_delta", 0)
            summary_lines.append(f"Score change from previous audit: {score_delta:+d} points.")

            if comparison.resolved_findings:
                resolved_titles = [f"{f.get('check_id')} ({f.get('title')})" for f in comparison.resolved_findings]
                summary_lines.append(f"Issues resolved since last audit: {', '.join(resolved_titles)}.")

            if comparison.persistent_findings:
                persistent_titles = [
                    f"{f.get('check_id')} (reoccurred {f.get('recurrence_count', 1)}x)"
                    for f in comparison.persistent_findings[:5]
                ]
                summary_lines.append(f"Persistent unresolved issues: {', '.join(persistent_titles)}.")

            if comparison.regressed_findings:
                regressed_titles = [f"{f.get('check_id')} ({f.get('title')})" for f in comparison.regressed_findings]
                summary_lines.append(f"Regressed issues (previously resolved, now reappeared): {', '.join(regressed_titles)}.")

            if comparison.new_findings:
                new_titles = [f"{f.get('check_id')} ({f.get('title')})" for f in comparison.new_findings[:5]]
                summary_lines.append(f"New issues detected: {', '.join(new_titles)}.")

            for impact in comparison.impact_observations:
                summary_lines.append(f"Outcome observation: {impact.observation_text}")
        else:
            summary_lines.append("This is the baseline audit for the website. No prior history exists.")

        durable_content = "\n".join(summary_lines)

        tags = ["audit_summary", f"audit_{comparison.audit_number}"]
        if comparison.resolved_findings:
            tags.append("has_resolved_issues")
        if comparison.regressed_findings:
            tags.append("has_regressions")

        metadata = {
            "domain": identity.domain,
            "audited_at": snapshot.audited_at,
            "audit_number": str(comparison.audit_number),
            "score_discoverability": str(snapshot.overall_scores.get("ai_discoverability_score", 0)),
            "score_engagement": str(snapshot.overall_scores.get("on_site_engagement_score", 0)),
        }

        # 3. Retain in Hindsight
        retained = self.client.retain(
            bank_id=bank_id,
            content=durable_content,
            metadata=metadata,
            tags=tags,
        )

        return retained

    def record_user_fix(
        self,
        identity: WebsiteIdentity,
        check_id: str,
        notes: str = "",
        action_summary: str = "",
    ) -> ImplementationEvent:
        """Record a user-confirmed implementation of a recommendation."""
        bank_id = identity.bank_id
        now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
        clean_time = now_iso.replace(":", "-").replace(".", "-")
        event_id = f"fix_{check_id}_{clean_time}"

        event = ImplementationEvent(
            event_id=event_id,
            domain=identity.domain,
            check_id=check_id,
            recorded_at=now_iso,
            status="user_confirmed",
            notes=notes,
            suggested_action_summary=action_summary,
        )

        # 1. Save local event
        self.client.save_local_event(bank_id, event.to_dict())

        # 2. Retain user action in Hindsight
        user_content = (
            f"User confirmed implementation of recommendation for finding '{check_id}' "
            f"on {now_iso}. "
            f"Action: {action_summary or 'No summary specified'}. "
            f"Notes from user: {notes or 'None'}. "
            f"Future audits should verify whether this issue remains detected or is resolved."
        )

        self.client.retain(
            bank_id=bank_id,
            content=user_content,
            metadata={"check_id": check_id, "event_type": "user_fix_confirmation"},
            tags=["user_action", check_id],
        )

        return event

    def reflect_on_history(self, identity: WebsiteIdentity) -> Optional[str]:
        """Perform higher-level reflective synthesis using Hindsight."""
        query = (
            f"Analyze the optimization history for {identity.domain}. "
            f"What changes followed previous recommendations? What worked, what did not, "
            f"what recurring problems remain, and what should be prioritized next?"
        )
        return self.client.reflect(bank_id=identity.bank_id, query=query)
