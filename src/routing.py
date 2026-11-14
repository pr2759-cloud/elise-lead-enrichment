"""Routing (v2): assign every lead an owner, with the reason.

Rules live in config.ROUTING_RULES and are checked in order; the first rule
whose conditions all hold wins. Changing who gets what is a config edit, not
a code change.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from . import config
from .heuristics.email import is_free_provider
from .models import CompanyEnrichment, Lead, LeadScore, NewsEnrichment


@dataclass(frozen=True)
class RouteContext:
    lead: Lead
    score: LeadScore
    company: CompanyEnrichment
    news: NewsEnrichment
    action: str


# condition name -> predicate(context, rule value) -> bool
_CONDITIONS: Dict[str, Callable[[RouteContext, Any], bool]] = {
    "tier_in": lambda c, v: c.score.tier in v,
    "action_in": lambda c, v: c.action in v,
    "multi_property": lambda c, v: bool(c.company.multi_property_signals) == bool(v),
    "has_trigger_30d": lambda c, v: bool(c.news.trigger_headline_30d) == bool(v),
    "free_email": lambda c, v: is_free_provider(c.lead.person_email) == bool(v),
    "min_confidence": lambda c, v: c.score.data_confidence >= v,
    "max_confidence": lambda c, v: c.score.data_confidence < v,
}


@dataclass(frozen=True)
class Route:
    route: str
    reason: str


def validate_rules(rules: List[Dict[str, Any]]) -> None:
    for i, rule in enumerate(rules):
        if "route" not in rule:
            raise ValueError(f"routing rule {i} has no 'route'")
        unknown = set(rule.get("when", {})) - set(_CONDITIONS)
        if unknown:
            raise ValueError(f"routing rule {i} uses unknown conditions: {sorted(unknown)}")


def route_lead(ctx: RouteContext, rules: Optional[List[Dict[str, Any]]] = None) -> Route:
    rules = config.ROUTING_RULES if rules is None else rules
    for rule in rules:
        when = rule.get("when", {})
        if all(_CONDITIONS[name](ctx, value) for name, value in when.items()):
            return Route(rule["route"], rule.get("reason", ""))
    return Route("unrouted", "no routing rule matched")


validate_rules(config.ROUTING_RULES)
