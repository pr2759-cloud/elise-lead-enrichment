"""Action gate (v2): decide what to do with a lead, not just how to score it.

v1 drafted an email for every lead, including cold ones. The gate adds the
judgment step: send, hand to a human, or stay silent.

    send   (Sniper)    score >= SEND_MIN_SCORE, enough real data, a business email
    review (Scout)     promising, or not well enough evidenced to trust the score
    silent (Archivist) below the outreach bar: recorded, no draft, no email
"""
from __future__ import annotations
from dataclasses import dataclass

from . import config
from .heuristics.email import is_free_provider
from .models import Lead, LeadScore


@dataclass(frozen=True)
class Decision:
    action: str   # "send" | "review" | "silent"
    reason: str


def decide(lead: Lead, score: LeadScore) -> Decision:
    s = score.final_score
    conf = score.data_confidence

    # Too little real data: the score is mostly neutral defaults, so neither a
    # send nor a silent drop is justified. A human decides.
    if conf < config.MIN_DATA_CONFIDENCE:
        return Decision(
            "review",
            f"only {conf:.0%} of signals resolved; the score is mostly neutral defaults",
        )

    if s < config.REVIEW_MIN_SCORE:
        return Decision("silent", f"score {s:.0f} is below the outreach bar ({config.REVIEW_MIN_SCORE:.0f})")

    if s >= config.SEND_MIN_SCORE:
        if is_free_provider(lead.person_email):
            return Decision("review", "high score but a personal email address; confirm the contact first")
        return Decision("send", f"score {s:.0f} with {conf:.0%} of signals resolved")

    return Decision("review", f"score {s:.0f} is promising but below the auto-send bar ({config.SEND_MIN_SCORE:.0f})")
