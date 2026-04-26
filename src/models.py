"""Data models for leads, enrichment results, scoring, and final output."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional, Any


@dataclass
class Lead:
    """Raw inbound lead as it arrives from the Sheet/CSV."""
    person_name: str
    person_email: str
    company: str
    property_address: str
    city: str
    state: str
    country: str = "US"

    @property
    def company_domain(self) -> Optional[str]:
        if "@" in self.person_email:
            return self.person_email.split("@", 1)[1].strip().lower()
        return None

    @property
    def first_name(self) -> str:
        return (self.person_name or "").split(" ", 1)[0] or "there"

    def fingerprint(self) -> str:
        """Stable hash-friendly string for deduplication / caching."""
        return f"{self.person_email.lower()}|{self.company.lower()}|{self.property_address.lower()}"


# ---------------------------------------------------------------------------
# Per-API enrichment results (each is "best effort" — missing data is None)
# ---------------------------------------------------------------------------
@dataclass
class CompanyEnrichment:
    has_wikipedia_page: bool = False
    wikipedia_title: Optional[str] = None
    wikipedia_summary: Optional[str] = None
    wikipedia_url: Optional[str] = None
    parent_mention_only: bool = False
    # Derived keyword flags
    matches_multifamily: bool = False
    matches_property_mgmt: bool = False
    matches_real_estate_owner: bool = False
    matches_adjacent: bool = False
    multi_property_signals: bool = False
    error: Optional[str] = None


@dataclass
class NewsEnrichment:
    articles_30d: int = 0
    articles_90d: int = 0
    trigger_headline_30d: Optional[str] = None
    trigger_headline_90d: Optional[str] = None
    trigger_url: Optional[str] = None
    has_tech_news: bool = False
    top_headline: Optional[str] = None
    top_url: Optional[str] = None
    error: Optional[str] = None


@dataclass
class MarketEnrichment:
    zip_code: Optional[str] = None
    median_gross_rent: Optional[float] = None
    renter_share: Optional[float] = None       # 0.0 - 1.0
    population: Optional[int] = None
    households: Optional[int] = None
    density_tier: Optional[str] = None         # "high" | "mid" | "low"
    error: Optional[str] = None


@dataclass
class LocationEnrichment:
    walk_score: Optional[int] = None
    transit_score: Optional[int] = None
    bike_score: Optional[int] = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------
@dataclass
class CategoryScore:
    name: str
    weight: float
    sub_signals: Dict[str, float] = field(default_factory=dict)  # label -> 0-10
    missing: List[str] = field(default_factory=list)

    @property
    def average(self) -> float:
        if not self.sub_signals:
            return 0.0
        return sum(self.sub_signals.values()) / len(self.sub_signals)

    @property
    def weighted_contribution(self) -> float:
        """Contribution to the final (0-10 scale) score."""
        return self.average * self.weight


@dataclass
class LeadScore:
    fit: CategoryScore
    value: CategoryScore
    timing: CategoryScore
    intent: CategoryScore

    @property
    def final_score(self) -> float:
        """Final score on 0-100 scale."""
        total = (
            self.fit.weighted_contribution
            + self.value.weighted_contribution
            + self.timing.weighted_contribution
            + self.intent.weighted_contribution
        )
        return round(total * 10, 1)  # 0-10 -> 0-100

    @property
    def tier(self) -> str:
        score = self.final_score
        if score >= 80:
            return "HOT"
        if score >= 60:
            return "WARM"
        if score >= 40:
            return "COOL"
        return "COLD"

    @property
    def missing_signals_count(self) -> int:
        return (
            len(self.fit.missing) + len(self.value.missing)
            + len(self.timing.missing) + len(self.intent.missing)
        )

    @property
    def total_signals_count(self) -> int:
        return (
            len(self.fit.sub_signals) + len(self.value.sub_signals)
            + len(self.timing.sub_signals) + len(self.intent.sub_signals)
        )


# ---------------------------------------------------------------------------
# Final output
# ---------------------------------------------------------------------------
@dataclass
class EnrichedLead:
    lead: Lead
    company: CompanyEnrichment
    news: NewsEnrichment
    market: MarketEnrichment
    location: LocationEnrichment
    score: LeadScore
    insights: str
    email_subject: str
    email_body: str
    processed_at: str = field(default_factory=lambda: datetime.utcnow().isoformat(timespec="seconds") + "Z")
    errors: List[str] = field(default_factory=list)

    def to_row(self) -> Dict[str, Any]:
        """Flatten to a dict suitable for a spreadsheet row."""
        return {
            "person_name": self.lead.person_name,
            "person_email": self.lead.person_email,
            "company": self.lead.company,
            "property_address": self.lead.property_address,
            "city": self.lead.city,
            "state": self.lead.state,
            "country": self.lead.country,
            "score": self.score.final_score,
            "tier": self.score.tier,
            "fit_score": round(self.score.fit.average, 2),
            "value_score": round(self.score.value.average, 2),
            "timing_score": round(self.score.timing.average, 2),
            "intent_score": round(self.score.intent.average, 2),
            "signals_resolved": f"{self.score.total_signals_count - self.score.missing_signals_count}/{self.score.total_signals_count}",
            "insights": self.insights,
            "email_subject": self.email_subject,
            "email_body": self.email_body,
            "wikipedia_url": self.company.wikipedia_url or "",
            "top_news_headline": self.news.top_headline or "",
            "top_news_url": self.news.top_url or "",
            "walk_score": self.location.walk_score if self.location.walk_score is not None else "",
            "median_rent": self.market.median_gross_rent if self.market.median_gross_rent is not None else "",
            "renter_share_pct": round(self.market.renter_share * 100, 1) if self.market.renter_share is not None else "",
            "status": "done" if not self.errors else "error",
            "error_summary": "; ".join(self.errors) if self.errors else "",
            "processed_at": self.processed_at,
        }


# ---------------------------------------------------------------------------
# Column order / schema for the Google Sheet & CSV output
# ---------------------------------------------------------------------------
INPUT_COLUMNS = [
    "person_name", "person_email", "company",
    "property_address", "city", "state", "country",
]

OUTPUT_COLUMNS = INPUT_COLUMNS + [
    "status", "score", "tier",
    "fit_score", "value_score", "timing_score", "intent_score",
    "signals_resolved", "insights", "email_subject", "email_body",
    "wikipedia_url", "top_news_headline", "top_news_url",
    "walk_score", "median_rent", "renter_share_pct",
    "error_summary", "processed_at",
]
