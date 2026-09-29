"""Memory-Aware Recommendation Agent for Nexora AI.

Enhances static findings and action plans with longitudinal context:
elevates recurring unresolved defects, flags regressions, incorporates user action
verification, and explains why specific tasks should be tackled next based on history.
"""

from typing import Dict, List, Any, Optional
from nexora.models import AuditComparison


class RecommendationAgent:
    """Agent that adapts and prioritizes recommendations based on historical memory."""

    def augment_recommendations(
        self,
        findings: List[Dict[str, Any]],
        action_plan: List[Dict[str, Any]],
        comparison: AuditComparison,
    ) -> Dict[str, Any]:
        """Augment findings and action plan with memory-driven historical annotations.
        
        Returns:
            dict containing:
              - 'findings': augmented findings list
              - 'action_plan': augmented sequenced action plan
              - 'memory_priority_headline': top priority recommendation with historical justification
              - 'recommended_focus': list of memory-highlighted actions
        """
        if comparison.is_first_audit:
            return {
                "findings": findings,
                "action_plan": action_plan,
                "memory_priority_headline": (
                    "Baseline recommendations sequenced by foundational pipeline stage. "
                    "Future audits will prioritize persistent issues and regressions."
                ),
                "recommended_focus": [],
            }

        persistent_map = {p["check_id"]: p for p in comparison.persistent_findings}
        regression_map = {r["check_id"]: r for r in comparison.regressed_findings}
        resolved_cids = {r["check_id"] for r in comparison.resolved_findings}

        recommended_focus = []

        # 1. Augment Findings with historical context
        augmented_findings = []
        for f in findings:
            f_copy = dict(f)
            cid = f_copy.get("check_id")
            sugg = dict(f_copy.get("suggested_action", {}))

            if cid in regression_map:
                reg_info = regression_map[cid]
                f_copy["historical_status"] = "regression"
                f_copy["history_context"] = (
                    "🚨 REGRESSION DETECTED: This issue was resolved in previous audits "
                    "but has reappeared in this audit."
                )
                # Elevate priority of regressions
                orig_priority = sugg.get("priority", "medium")
                if orig_priority in ("medium", "low"):
                    sugg["priority"] = "high"
                sugg["detail"] = (
                    (sugg.get("detail", "") + " ").strip()
                    + " [Historical Note: This is a regression from a previously passing state; check recent code or template changes.]"
                ).strip()
                recommended_focus.append({
                    "finding_id": f_copy.get("id"),
                    "check_id": cid,
                    "title": f_copy.get("title"),
                    "reason": "Regression of previously resolved defect",
                    "action": sugg.get("summary", ""),
                    "priority": sugg.get("priority", "high"),
                })

            elif cid in persistent_map:
                p_info = persistent_map[cid]
                count = p_info.get("recurrence_count", 2)
                f_copy["historical_status"] = "persistent"
                f_copy["recurrence_count"] = count

                if p_info.get("status") == "unresolved_despite_user_fix":
                    f_copy["history_context"] = (
                        f"⚠️ PERSISTENT (Fix Ineffective): Marked as fixed in previous cycle, "
                        f"but remains detected in crawler evidence across {count} audits."
                    )
                    sugg["detail"] = (
                        (sugg.get("detail", "") + " ").strip()
                        + f" [Historical Note: Fix was logged previously but issue is still observed. Re-verify implementation against live URL.]"
                    ).strip()
                else:
                    f_copy["history_context"] = (
                        f"⚠️ CHRONIC UNRESOLVED: Detected across {count} consecutive audit cycles."
                    )
                    sugg["detail"] = (
                        (sugg.get("detail", "") + " ").strip()
                        + f" [Historical Note: Has persisted across {count} audit cycles.]"
                    ).strip()

                if count >= 2:
                    recommended_focus.append({
                        "finding_id": f_copy.get("id"),
                        "check_id": cid,
                        "title": f_copy.get("title"),
                        "reason": f"Unresolved across {count} consecutive audits",
                        "action": sugg.get("summary", ""),
                        "priority": sugg.get("priority", "medium"),
                    })

            else:
                f_copy["historical_status"] = "new"
                f_copy["history_context"] = "Newly detected issue not present in previous audit."

            f_copy["suggested_action"] = sugg
            augmented_findings.append(f_copy)

        # 2. Augment Action Plan
        augmented_plan = []
        for stage in action_plan:
            stage_copy = dict(stage)
            actions = []
            for act in stage.get("actions", []):
                act_copy = dict(act)
                fid = act_copy.get("finding_id")
                matching_f = next((f for f in augmented_findings if f.get("id") == fid), None)
                if matching_f:
                    if matching_f.get("historical_status") == "regression":
                        act_copy["action"] = "[REGRESSION] " + act_copy["action"]
                        act_copy["priority_elevation"] = "Elevated due to regression"
                    elif matching_f.get("historical_status") == "persistent" and matching_f.get("recurrence_count", 1) >= 2:
                        count = matching_f.get("recurrence_count")
                        act_copy["action"] = f"[PERSISTENT {count}x] " + act_copy["action"]
                        act_copy["priority_elevation"] = f"Elevated: persistent across {count} audits"
                actions.append(act_copy)
            stage_copy["actions"] = actions
            augmented_plan.append(stage_copy)

        # 3. Formulate memory-aware headline / executive reason
        headline = self._synthesize_headline(comparison, recommended_focus)

        return {
            "findings": augmented_findings,
            "action_plan": augmented_plan,
            "memory_priority_headline": headline,
            "recommended_focus": recommended_focus,
        }

    def _synthesize_headline(
        self,
        comparison: AuditComparison,
        recommended_focus: List[Dict[str, Any]],
    ) -> str:
        """Formulate the central memory-aware recommendation answering 'Why this next?'."""
        resolved = comparison.resolved_findings
        regressed = comparison.regressed_findings
        persistent = comparison.persistent_findings

        if regressed:
            r_titles = ", ".join(f"`{r['check_id']}`" for r in regressed[:2])
            return (
                f"Urgent Priority: Address regression in {r_titles}. "
                "This defect was previously resolved but has returned, threatening prior citation gains."
            )

        if persistent and resolved:
            top_p = persistent[0]
            resolved_count = len(resolved)
            return (
                f"Prioritize `{top_p['check_id']}` ({top_p['title']}): "
                f"It has remained unresolved across {top_p.get('recurrence_count', 2)} audit cycles, "
                f"while {resolved_count} foundational defect(s) were successfully resolved."
            )

        if persistent:
            top_p = persistent[0]
            return (
                f"Prioritize `{top_p['check_id']}`: Unresolved across "
                f"{top_p.get('recurrence_count', 2)} audit cycles."
            )

        return (
            "Prioritize remaining foundational issues according to the staged pipeline."
        )
