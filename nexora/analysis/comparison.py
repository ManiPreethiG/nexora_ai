"""Audit Comparison Engine for Nexora AI.

Performs deterministic comparison between current and historical audit snapshots.
Identifies resolved findings, persistent issues, new defects, and regressions.
"""

from typing import Dict, List, Any, Optional, Set
from nexora.models import (
    AuditSnapshot,
    FindingSnapshot,
    ImplementationEvent,
    AuditComparison,
    ImpactObservation,
)


class ComparisonAgent:
    """Agent responsible for analyzing changes between historical audits and current state."""

    def compare(
        self,
        current_snapshot: AuditSnapshot,
        previous_snapshots: List[AuditSnapshot],
        user_events: Optional[List[ImplementationEvent]] = None,
    ) -> AuditComparison:
        """Compare current audit with historical sequence."""
        user_events = user_events or []
        user_event_checks = {e.check_id: e for e in user_events}

        if not previous_snapshots:
            # Baseline First Audit
            return AuditComparison(
                is_first_audit=True,
                audit_number=1,
                previous_snapshot_id=None,
                current_snapshot_id=current_snapshot.snapshot_id,
                audited_at_prev=None,
                audited_at_curr=current_snapshot.audited_at,
                score_changes={
                    "ai_discoverability_delta": 0,
                    "on_site_engagement_delta": 0,
                    "total_findings_delta": 0,
                },
                resolved_findings=[],
                persistent_findings=[],
                new_findings=[],
                regressed_findings=[],
                user_actions=[e.to_dict() for e in user_events],
                impact_observations=[],
                learned_insights=[
                    "Baseline audit established. Subsequent audits will track finding resolution, "
                    "persistence, regressions, and score impact."
                ],
            )

        prev = previous_snapshots[-1]
        audit_number = len(previous_snapshots) + 1

        curr_by_check = {f.check_id: f for f in current_snapshot.findings}
        prev_by_check = {f.check_id: f for f in prev.findings}

        curr_ids = set(curr_by_check.keys())
        prev_ids = set(prev_by_check.keys())

        # Historical set across all snapshots prior to `prev`
        historical_older_ids: Set[str] = set()
        for older in previous_snapshots[:-1]:
            historical_older_ids.update(f.check_id for f in older.findings)

        # 1. Resolved issues: in previous, NOT in current
        resolved_findings: List[Dict[str, Any]] = []
        for cid in prev_ids - curr_ids:
            old_f = prev_by_check[cid]
            user_ev = user_event_checks.get(cid)
            status = "user_confirmed_and_resolved" if user_ev else "observed_resolved"
            resolved_findings.append({
                "check_id": cid,
                "id": old_f.id,
                "title": old_f.title,
                "category": old_f.category,
                "severity": old_f.severity,
                "status": status,
                "user_notes": user_ev.notes if user_ev else "",
                "evidence_prior": old_f.evidence,
            })

        # 2. Persistent issues: in both previous AND current
        persistent_findings: List[Dict[str, Any]] = []
        for cid in prev_ids & curr_ids:
            curr_f = curr_by_check[cid]
            user_ev = user_event_checks.get(cid)

            # Calculate recurrence count across all previous snapshots
            reoccurrences = 1
            for older in reversed(previous_snapshots[:-1]):
                if cid in {f.check_id for f in older.findings}:
                    reoccurrences += 1
                else:
                    break  # consecutive chain broken

            status = "unresolved_despite_user_fix" if user_ev else "persistent"

            persistent_findings.append({
                "check_id": cid,
                "id": curr_f.id,
                "title": curr_f.title,
                "category": curr_f.category,
                "severity": curr_f.severity,
                "recurrence_count": reoccurrences + 1,  # including current
                "status": status,
                "user_notes": user_ev.notes if user_ev else "",
                "evidence": curr_f.evidence,
                "suggested_action": curr_f.suggested_action,
            })

        # 3. New issues vs Regressions:
        # In current, NOT in previous
        new_candidate_ids = curr_ids - prev_ids
        new_findings: List[Dict[str, Any]] = []
        regressed_findings: List[Dict[str, Any]] = []

        for cid in new_candidate_ids:
            curr_f = curr_by_check[cid]
            if cid in historical_older_ids:
                # Issue existed in older audits, was absent in `prev`, and now reappeared!
                regressed_findings.append({
                    "check_id": cid,
                    "id": curr_f.id,
                    "title": curr_f.title,
                    "category": curr_f.category,
                    "severity": curr_f.severity,
                    "status": "regression",
                    "evidence": curr_f.evidence,
                    "suggested_action": curr_f.suggested_action,
                    "history_note": "Previously detected in earlier audits, was resolved, but has now regressed.",
                })
            else:
                new_findings.append({
                    "check_id": cid,
                    "id": curr_f.id,
                    "title": curr_f.title,
                    "category": curr_f.category,
                    "severity": curr_f.severity,
                    "status": "new",
                    "evidence": curr_f.evidence,
                    "suggested_action": curr_f.suggested_action,
                })

        # Score changes
        score_changes = {
            "ai_discoverability_delta": (
                current_snapshot.overall_scores.get("ai_discoverability_score", 0)
                - prev.overall_scores.get("ai_discoverability_score", 0)
            ),
            "on_site_engagement_delta": (
                current_snapshot.overall_scores.get("on_site_engagement_score", 0)
                - prev.overall_scores.get("on_site_engagement_score", 0)
            ),
            "total_findings_delta": current_snapshot.total_findings - prev.total_findings,
        }

        # Compute impact observations and learned insights
        impact_observations = self._analyze_impact(
            resolved_findings=resolved_findings,
            score_changes=score_changes,
            prev=prev,
            curr=current_snapshot,
        )

        learned_insights = self._derive_insights(
            resolved=resolved_findings,
            persistent=persistent_findings,
            regressed=regressed_findings,
            new=new_findings,
            score_changes=score_changes,
        )

        return AuditComparison(
            is_first_audit=False,
            audit_number=audit_number,
            previous_snapshot_id=prev.snapshot_id,
            current_snapshot_id=current_snapshot.snapshot_id,
            audited_at_prev=prev.audited_at,
            audited_at_curr=current_snapshot.audited_at,
            score_changes=score_changes,
            resolved_findings=resolved_findings,
            persistent_findings=persistent_findings,
            new_findings=new_findings,
            regressed_findings=regressed_findings,
            user_actions=[e.to_dict() for e in user_events],
            impact_observations=impact_observations,
            learned_insights=learned_insights,
        )

    def _analyze_impact(
        self,
        resolved_findings: List[Dict[str, Any]],
        score_changes: Dict[str, int],
        prev: AuditSnapshot,
        curr: AuditSnapshot,
    ) -> List[ImpactObservation]:
        """Formulate careful, non-causal impact observations connecting resolved findings with score movement."""
        observations: List[ImpactObservation] = []
        disc_delta = score_changes.get("ai_discoverability_delta", 0)
        eng_delta = score_changes.get("on_site_engagement_delta", 0)

        for rf in resolved_findings:
            cid = rf["check_id"]
            title = rf["title"]
            cat = rf["category"]
            is_user_confirmed = rf["status"] == "user_confirmed_and_resolved"

            if cat in ("discoverability", "both") and disc_delta != 0:
                direction = "an increase" if disc_delta > 0 else "a decrease"
                prefix = (
                    "Following confirmed user implementation, the resolution of"
                    if is_user_confirmed else "The resolution of"
                )
                obs_text = (
                    f"{prefix} '{title}' ({cid}) coincided with {direction} of "
                    f"{abs(disc_delta)} points in AI Discoverability "
                    f"({prev.overall_scores.get('ai_discoverability_score', 0)} → "
                    f"{curr.overall_scores.get('ai_discoverability_score', 0)})."
                )
                observations.append(ImpactObservation(
                    check_id=cid,
                    finding_title=title,
                    resolution_type="user_confirmed_fix" if is_user_confirmed else "observed_resolution",
                    score_metric="ai_discoverability_score",
                    score_delta=disc_delta,
                    observation_text=obs_text,
                ))

            if cat in ("engagement", "both") and eng_delta != 0:
                direction = "an increase" if eng_delta > 0 else "a decrease"
                obs_text = (
                    f"Resolution of '{title}' was associated with {direction} of "
                    f"{abs(eng_delta)} points in On-site Engagement "
                    f"({prev.overall_scores.get('on_site_engagement_score', 0)} → "
                    f"{curr.overall_scores.get('on_site_engagement_score', 0)})."
                )
                observations.append(ImpactObservation(
                    check_id=cid,
                    finding_title=title,
                    resolution_type="user_confirmed_fix" if is_user_confirmed else "observed_resolution",
                    score_metric="on_site_engagement_score",
                    score_delta=eng_delta,
                    observation_text=obs_text,
                ))

        return observations

    def _derive_insights(
        self,
        resolved: List[Dict[str, Any]],
        persistent: List[Dict[str, Any]],
        regressed: List[Dict[str, Any]],
        new: List[Dict[str, Any]],
        score_changes: Dict[str, int],
    ) -> List[str]:
        """Synthesize high-level patterns from the delta."""
        insights = []
        disc_delta = score_changes.get("ai_discoverability_delta", 0)

        if resolved and disc_delta > 0:
            resolved_names = ", ".join(f["check_id"] for f in resolved[:3])
            insights.append(
                f"Resolving {resolved_names} followed an improvement of +{disc_delta} points "
                "in AI Discoverability, confirming the effectiveness of addressing foundational crawl and markup barriers."
            )

        high_persistent = [p for p in persistent if p.get("recurrence_count", 1) >= 2]
        if high_persistent:
            p_names = ", ".join(f"{p['check_id']} ({p.get('recurrence_count')} audits)" for p in high_persistent[:3])
            insights.append(
                f"Recurring unresolved issues detected: {p_names}. These represent sticky structural "
                "or content debt that should be prioritized over new secondary refinements."
            )

        if regressed:
            r_names = ", ".join(r["check_id"] for r in regressed)
            insights.append(
                f"Regression alert: {r_names} reappeared after being absent in the previous audit. "
                "Review recent deployments or template rollbacks to restore previous passing state."
            )

        unresolved_fixes = [p for p in persistent if p.get("status") == "unresolved_despite_user_fix"]
        if unresolved_fixes:
            u_names = ", ".join(u["check_id"] for u in unresolved_fixes)
            insights.append(
                f"Implementation discrepancy: {u_names} was logged as fixed by user, but the defect "
                "is still detected in current crawler evidence. Verify configuration or caching."
            )

        return insights
