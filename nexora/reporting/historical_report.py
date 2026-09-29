"""Historical Report Serializer and Markdown Generator for Nexora AI.

Enriches the standard audit report with longitudinal tracking, score deltas,
resolved/persistent/regression breakdowns, and memory-aware priorities.
"""

from typing import Dict, Any, List
from nexora.models import AuditComparison


def augment_report(
    report: Dict[str, Any],
    comparison: AuditComparison,
    recommendation_augmentation: Dict[str, Any],
) -> Dict[str, Any]:
    """Merge historical comparison and memory-aware recommendations into report dict."""
    augmented = dict(report)

    # 1. Update findings and action plan with augmented versions
    if "findings" in recommendation_augmentation:
        augmented["findings"] = recommendation_augmentation["findings"]
    if "action_plan" in recommendation_augmentation:
        augmented["action_plan"] = recommendation_augmentation["action_plan"]

    # 2. Add top-level historical_context block
    hist_ctx = comparison.to_dict()
    hist_ctx["memory_priority_headline"] = recommendation_augmentation.get("memory_priority_headline", "")
    hist_ctx["recommended_focus"] = recommendation_augmentation.get("recommended_focus", [])
    augmented["historical_context"] = hist_ctx

    # 3. Augment summary with delta indicators
    summary = dict(augmented.get("summary", {}))
    if not comparison.is_first_audit:
        summary["historical_delta_discoverability"] = comparison.score_changes.get("ai_discoverability_delta", 0)
        summary["historical_delta_engagement"] = comparison.score_changes.get("on_site_engagement_delta", 0)
        summary["memory_headline"] = recommendation_augmentation.get("memory_priority_headline", "")
    augmented["summary"] = summary

    return augmented


def to_historical_markdown(r: Dict[str, Any]) -> str:
    """Generate comprehensive human-readable Markdown report with historical memory section."""
    L = []
    a = L.append
    site = r.get("site", "unknown")
    audited_at = r.get("audited_at", "")
    site_type = r.get("site_profile", {}).get("site_type", "unclassified")
    pages_crawled = r.get("scope", {}).get("pages_crawled", 0)
    summary = r.get("summary", {})
    hist = r.get("historical_context", {})
    is_first_audit = hist.get("is_first_audit", True)
    audit_num = hist.get("audit_number", 1)

    a(f"# Nexora AI Audit Report — {site}")
    a("")
    a(f"*Audit Cycle #{audit_num} · {audited_at} · {site_type} site · {pages_crawled} pages sampled*")
    a("")

    # Headline
    if not is_first_audit and hist.get("memory_priority_headline"):
        a(f"> 💡 **Memory-Driven Priority:** {hist['memory_priority_headline']}")
        a("")
    a(f"**{summary.get('headline', '')}**")
    a("")

    # Scorecard Table
    a("## Audit Scorecard")
    a("")
    if is_first_audit:
        a("| Dimension | Current Score | Status |")
        a("|---|---|---|")
        a(f"| **AI Discoverability** | **{summary.get('ai_discoverability_score', 0)}/100** | Baseline established |")
        a(f"| **On-site Engagement** | **{summary.get('on_site_engagement_score', 0)}/100** | Baseline established |")
        a(f"| Total Findings | {summary.get('total_findings', 0)} ({summary.get('critical', 0)} crit, {summary.get('high', 0)} high, {summary.get('medium', 0)} med, {summary.get('low', 0)} low) | — |")
    else:
        disc_curr = summary.get("ai_discoverability_score", 0)
        disc_delta = hist.get("score_changes", {}).get("ai_discoverability_delta", 0)
        disc_prev = disc_curr - disc_delta

        eng_curr = summary.get("on_site_engagement_score", 0)
        eng_delta = hist.get("score_changes", {}).get("on_site_engagement_delta", 0)
        eng_prev = eng_curr - eng_delta

        disc_delta_str = f"+{disc_delta}" if disc_delta > 0 else str(disc_delta)
        eng_delta_str = f"+{eng_delta}" if eng_delta > 0 else str(eng_delta)

        a("| Dimension | Previous | Current | Delta | Status |")
        a("|---|---|---|---|---|")
        a(f"| **AI Discoverability** | {disc_prev}/100 | **{disc_curr}/100** | **{disc_delta_str}** | {'🟢 Improved' if disc_delta > 0 else ('🔴 Declined' if disc_delta < 0 else '⚪ Unchanged')} |")
        a(f"| **On-site Engagement** | {eng_prev}/100 | **{eng_curr}/100** | **{eng_delta_str}** | {'🟢 Improved' if eng_delta > 0 else ('🔴 Declined' if eng_delta < 0 else '⚪ Unchanged')} |")
        a(f"| Total Findings | {summary.get('total_findings', 0) - hist.get('score_changes', {}).get('total_findings_delta', 0)} | **{summary.get('total_findings', 0)}** | {hist.get('score_changes', {}).get('total_findings_delta', 0):+d} | {summary.get('critical', 0)} crit, {summary.get('high', 0)} high, {summary.get('medium', 0)} med |")

    a("")

    # Longitudinal History Section
    a("## Longitudinal Memory & Changes")
    a("")
    if is_first_audit:
        a("*This is the first recorded audit for this website. Future audits will compare changes against this baseline in Hindsight persistent memory.*")
    else:
        a(f"*Compared against previous audit from {hist.get('audited_at_prev', 'earlier')}.*")
        a("")

        # 1. Regressions
        regressed = hist.get("regressed_findings", [])
        if regressed:
            a("### 🚨 Regressions Detected")
            a("")
            a("These issues were resolved in earlier audits but have now reappeared:")
            a("")
            for r_item in regressed:
                a(f"- **`{r_item.get('check_id')}` ({r_item.get('title')})** — *{r_item.get('severity', '').upper()}*")
                a(f"  - **Evidence:** {r_item.get('evidence')}")
                a(f"  - **Action Required:** {r_item.get('suggested_action', {}).get('summary', '')}")
            a("")

        # 2. Resolved
        resolved = hist.get("resolved_findings", [])
        if resolved:
            a("### ✅ Resolved Issues")
            a("")
            a("The following issues were detected previously and are no longer found on the sampled pages:")
            a("")
            for res in resolved:
                verified_tag = "*(User Confirmed Fix)*" if res.get("status") == "user_confirmed_and_resolved" else "*(Observed Resolved)*"
                a(f"- **`{res.get('check_id')}` — {res.get('title')}** {verified_tag}")
                if res.get("user_notes"):
                    a(f"  - *User Implementation Note:* {res.get('user_notes')}")
            a("")

        # 3. Persistent
        persistent = hist.get("persistent_findings", [])
        if persistent:
            a("### ⏳ Persistent Issues")
            a("")
            a("The following issues remain unresolved across multiple audit cycles:")
            a("")
            for p in persistent:
                rec_count = p.get("recurrence_count", 2)
                flag = " ⚠️ *(Marked fixed by user, but still detected!)*" if p.get("status") == "unresolved_despite_user_fix" else ""
                a(f"- **`{p.get('check_id')}` — {p.get('title')}** *(Present for {rec_count} consecutive cycles)*{flag}")
                a(f"  - **Priority Action:** {p.get('suggested_action', {}).get('summary', '')}")
            a("")

        # 4. New
        new_items = hist.get("new_findings", [])
        if new_items:
            a("### 🆕 Newly Detected Issues")
            a("")
            for n in new_items:
                a(f"- **`{n.get('check_id')}` — {n.get('title')}** *({n.get('severity', '').upper()})*")
            a("")

        # 5. Learned Insights & Impact
        impacts = hist.get("impact_observations", [])
        insights = hist.get("learned_insights", [])
        if impacts or insights:
            a("### 🧠 Learned Insights & Historical Impact")
            a("")
            for imp in impacts:
                a(f"- **Impact Observation:** {imp.get('observation_text')}")
            for ins in insights:
                a(f"- **Pattern:** {ins}")
            a("")

    # Current Findings
    a("## Current Findings")
    for f in r.get("findings", []):
        a("")
        badge = ""
        if f.get("historical_status") == "regression":
            badge = " [🚨 REGRESSION]"
        elif f.get("historical_status") == "persistent":
            badge = f" [⏳ PERSISTENT {f.get('recurrence_count', 1)}x]"
        elif f.get("historical_status") == "new":
            badge = " [🆕 NEW]"

        a(f"### {f['id']} · {f['severity'].upper()} — {f['title']}{badge}")
        a("")
        a(f"- **Category:** {f.get('category', '-')} · **Confidence:** {f.get('confidence', '-')} · **Source check:** `{f.get('check_id', '-')}`")
        if f.get("history_context"):
            a(f"- **Historical Context:** {f.get('history_context')}")
        a(f"- **Evidence:** {f['evidence']}")
        if f.get("mechanism"):
            a(f"- **Why it matters:** {f['mechanism']}")
        sugg = f.get("suggested_action", {})
        a(f"- **Fix ({sugg.get('effort', '-')} effort, {sugg.get('priority', '-')} priority):** {sugg.get('summary', '')}")
        if sugg.get("detail"):
            a(f"- **How:** {sugg.get('detail')}")
        if sugg.get("verification"):
            a(f"- **Verify:** {sugg.get('verification')}")
        if f.get("affected_urls"):
            a(f"- **Affected:** {', '.join(f['affected_urls'][:5])}")

    # Action Plan
    a("")
    a("## Fix in this order")
    for stage in r.get("action_plan", []):
        a("")
        a(f"**{stage['stage']}** — {stage['why_this_order']}")
        a("")
        for act in stage.get("actions", []):
            elev = f" *({act.get('priority_elevation')})*" if act.get("priority_elevation") else ""
            a(f"- `{act['finding_id']}` ({act['severity']}, {act['effort']} effort){elev} {act['action']}")

    # Proactive recommendations
    a("")
    a("## Worth doing even with no defect found")
    for rec in r.get("proactive_recommendations", []):
        a("")
        a(f"**{rec['title']}**  ")
        a(f"{rec['detail']}")

    # Limitations
    a("")
    a("## What this audit could not check")
    for lim in r.get("limitations", []):
        a(f"- {lim}")

    # Checks not fired
    a("")
    a("## Checks deliberately not fired")
    a("")
    a("These were evaluated and found not to apply — recorded so the report can be trusted to have looked.")
    a("")
    for n in r.get("checks_not_applicable", [])[:40]:
        a(f"- `{n.get('check_id', '?')}` — {n.get('reason', '')}")

    return "\n".join(L)
