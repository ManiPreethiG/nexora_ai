"""Data models and schemas for Nexora AI longitudinal audits, snapshots, and memory.
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Any, Optional
import datetime as dt
import re


@dataclass
class FindingSnapshot:
    """Compact, durable snapshot of an individual audit finding."""
    check_id: str
    id: str
    title: str
    category: str
    concern: str
    severity: str
    confidence: str
    evidence: str
    affected_urls: List[str] = field(default_factory=list)
    suggested_action: Dict[str, Any] = field(default_factory=dict)
    mechanism: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FindingSnapshot":
        return cls(
            check_id=data.get("check_id") or data.get("id") or "UNKNOWN",
            id=data.get("id", ""),
            title=data.get("title", ""),
            category=data.get("category", "both"),
            concern=data.get("concern", ""),
            severity=data.get("severity", "medium"),
            confidence=data.get("confidence", "high"),
            evidence=data.get("evidence", ""),
            affected_urls=data.get("affected_urls", []) or [],
            suggested_action=data.get("suggested_action", {}) or {},
            mechanism=data.get("mechanism", "") or "",
        )


@dataclass
class AuditSnapshot:
    """Historical audit snapshot capturing key metrics and findings without raw HTML."""
    snapshot_id: str
    domain: str
    audited_at: str
    overall_scores: Dict[str, int]
    severity_counts: Dict[str, int]
    total_findings: int
    findings: List[FindingSnapshot] = field(default_factory=list)
    site_type: Optional[str] = None
    brand_name: Optional[str] = None
    headline: str = ""
    pages_crawled: int = 0
    checks_not_applicable: List[Dict[str, str]] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["findings"] = [f.to_dict() if isinstance(f, FindingSnapshot) else f for f in self.findings]
        return d

    @property
    def check_ids(self) -> set:
        return {f.check_id for f in self.findings}

    @classmethod
    def from_report(cls, report: Dict[str, Any]) -> "AuditSnapshot":
        """Convert a standard orchestrator report dict into an AuditSnapshot."""
        audited_at = report.get("audited_at") or dt.datetime.now(dt.timezone.utc).isoformat()
        site = report.get("site", "unknown")
        summary = report.get("summary", {})
        scope = report.get("scope", {})
        profile = report.get("site_profile", {})

        clean_site = re.sub(r"[^a-zA-Z0-9_-]", "_", site).strip("_")
        clean_time = re.sub(r"[^a-zA-Z0-9_-]", "_", audited_at).strip("_")
        snapshot_id = f"snap_{clean_site}_{clean_time}"

        findings = [
            FindingSnapshot.from_dict(f) for f in report.get("findings", [])
        ]

        return cls(
            snapshot_id=snapshot_id,
            domain=site,
            audited_at=audited_at,
            overall_scores={
                "ai_discoverability_score": summary.get("ai_discoverability_score", 0),
                "on_site_engagement_score": summary.get("on_site_engagement_score", 0),
            },
            severity_counts={
                "critical": summary.get("critical", 0),
                "high": summary.get("high", 0),
                "medium": summary.get("medium", 0),
                "low": summary.get("low", 0),
            },
            total_findings=summary.get("total_findings", len(findings)),
            findings=findings,
            site_type=profile.get("site_type"),
            brand_name=profile.get("brand_name"),
            headline=summary.get("headline", ""),
            pages_crawled=scope.get("pages_crawled", 0),
            checks_not_applicable=report.get("checks_not_applicable", []),
            limitations=report.get("limitations", []),
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AuditSnapshot":
        findings = [
            FindingSnapshot.from_dict(f) if isinstance(f, dict) else f
            for f in data.get("findings", [])
        ]
        return cls(
            snapshot_id=data.get("snapshot_id", ""),
            domain=data.get("domain", ""),
            audited_at=data.get("audited_at", ""),
            overall_scores=data.get("overall_scores", {}),
            severity_counts=data.get("severity_counts", {}),
            total_findings=data.get("total_findings", len(findings)),
            findings=findings,
            site_type=data.get("site_type"),
            brand_name=data.get("brand_name"),
            headline=data.get("headline", ""),
            pages_crawled=data.get("pages_crawled", 0),
            checks_not_applicable=data.get("checks_not_applicable", []),
            limitations=data.get("limitations", []),
        )


@dataclass
class ImplementationEvent:
    """User-confirmed or verified action taken to fix a finding."""
    event_id: str
    domain: str
    check_id: str
    recorded_at: str
    status: str  # "user_confirmed", "observed_resolved", "reverted"
    notes: str = ""
    suggested_action_summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ImplementationEvent":
        return cls(
            event_id=data.get("event_id", ""),
            domain=data.get("domain", ""),
            check_id=data.get("check_id", ""),
            recorded_at=data.get("recorded_at", ""),
            status=data.get("status", "user_confirmed"),
            notes=data.get("notes", ""),
            suggested_action_summary=data.get("suggested_action_summary", ""),
        )


@dataclass
class ImpactObservation:
    """Measurement of score and health movement following finding resolution."""
    check_id: str
    finding_title: str
    resolution_type: str  # "user_confirmed_fix" or "observed_resolution"
    score_metric: str     # "ai_discoverability_score" or "on_site_engagement_score"
    score_delta: int
    observation_text: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AuditComparison:
    """Comparison between previous and current audit snapshots."""
    is_first_audit: bool
    audit_number: int
    previous_snapshot_id: Optional[str]
    current_snapshot_id: str
    audited_at_prev: Optional[str]
    audited_at_curr: str
    score_changes: Dict[str, int]
    resolved_findings: List[Dict[str, Any]]
    persistent_findings: List[Dict[str, Any]]
    new_findings: List[Dict[str, Any]]
    regressed_findings: List[Dict[str, Any]]
    user_actions: List[Dict[str, Any]]
    impact_observations: List[ImpactObservation]
    learned_insights: List[str]

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["impact_observations"] = [io.to_dict() if isinstance(io, ImpactObservation) else io
                                    for io in self.impact_observations]
        return d
