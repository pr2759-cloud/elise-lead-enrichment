"""Email-based heuristics: domain quality and role seniority inference."""
from __future__ import annotations
import re
from typing import Optional


FREE_PROVIDERS = {
    "gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "aol.com",
    "icloud.com", "me.com", "mac.com", "live.com", "msn.com",
    "proton.me", "protonmail.com", "pm.me",
    "yandex.com", "zoho.com", "gmx.com", "mail.com", "fastmail.com",
}

EXECUTIVE_KEYWORDS = [
    "ceo", "cto", "cfo", "coo", "cmo", "cpo", "cro", "ciso", "chief",
    "president", "founder", "cofounder", "co-founder",
    "vp", "vice president", "svp", "evp",
    "head of", "head-of",
    "director",
    "partner",
    "principal",
    "owner",
]

MANAGER_KEYWORDS = [
    "manager", "mgr", "lead", "senior", "sr.", "sr ",
    "supervisor", "coordinator",
]

GENERIC_ALIASES = {
    "info", "contact", "hello", "sales", "leasing", "leads",
    "admin", "support", "noreply", "no-reply", "office",
    "team", "general",
}


def is_free_provider(email: str) -> bool:
    if not email or "@" not in email:
        return False
    domain = email.split("@", 1)[1].strip().lower()
    return domain in FREE_PROVIDERS


def extract_domain(email: str) -> Optional[str]:
    if not email or "@" not in email:
        return None
    return email.split("@", 1)[1].strip().lower()


def email_quality_score(email: str) -> float:
    """Intent sub-signal: 0-10 based on domain quality."""
    if not email or "@" not in email:
        return 0.0
    domain = extract_domain(email)
    if not domain:
        return 0.0
    if is_free_provider(email):
        return 3.0
    # Looks like a corporate domain
    return 10.0


def seniority_score(person_name: str, email: str, title_hint: Optional[str] = None) -> float:
    """Fit sub-signal: 0-10 based on role seniority inferred from available signals."""
    # 1. Generic alias in the local-part of the email is a strong negative signal
    local_part = ""
    if email and "@" in email:
        local_part = email.split("@", 1)[0].strip().lower()
        local_part_core = re.sub(r"[^a-z]", "", local_part)
        if local_part_core in GENERIC_ALIASES or local_part.split(".")[0] in GENERIC_ALIASES:
            return 3.0

    haystack_parts = [s.lower() for s in [person_name or "", title_hint or "", local_part] if s]
    haystack = " ".join(haystack_parts)

    for kw in EXECUTIVE_KEYWORDS:
        if kw in haystack:
            return 10.0
    for kw in MANAGER_KEYWORDS:
        if kw in haystack:
            return 7.0

    # Name-only, no title — neutral-ish individual contributor
    return 5.0
