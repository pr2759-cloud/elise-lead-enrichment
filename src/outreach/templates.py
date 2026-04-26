"""Email templates keyed by dominant scoring category.

Each template is a (subject, body) tuple using Python str.format placeholders.
"""
from __future__ import annotations
from typing import Dict, Tuple


# Template keys correspond to the selection logic in email_drafter.py.
TEMPLATES: Dict[str, Tuple[str, str]] = {
    "trigger_event": (
        "Re: {trigger_headline_short}",
        "Hi {first_name},\n\n"
        "Saw the news about {company} — {trigger_headline}. Congrats on the momentum.\n\n"
        "With everything expanding at {company}, leasing response times tend to become "
        "the bottleneck right around now. EliseAI handles resident inquiries 24/7 — SMS, "
        "email, and chat — so your leasing team can focus on tours and conversions instead "
        "of triaging the inbox.\n\n"
        "Worth a 15-minute call to see if it fits your workflow?\n\n"
        "Best,\n{sender_name}"
    ),
    "scale": (
        "Leasing automation for {company}",
        "Hi {first_name},\n\n"
        "{company} is one of the more established operators in the space, and at that scale, "
        "even a small lift in lead-to-tour conversion compounds quickly across the portfolio.\n\n"
        "EliseAI automates the first touch with every prospective resident — pricing questions, "
        "tour scheduling, application follow-up — so your team can focus on the qualified ones. "
        "Portfolio-wide rollouts typically pay back within the first leasing cycle.\n\n"
        "Happy to share a short demo tailored to {company}'s footprint. Does sometime this week work?\n\n"
        "Best,\n{sender_name}"
    ),
    "premium_market": (
        "Prospect response times at {property_ref}",
        "Hi {first_name},\n\n"
        "{property_ref} sits in a strong rental market — {market_fact}. In markets like that, "
        "prospective residents often tour multiple properties on the same day, so the first "
        "operator to respond usually wins the lease.\n\n"
        "EliseAI responds to every inquiry in seconds, 24/7, and schedules tours automatically. "
        "Teams at comparable operators have seen measurable lifts in tour booking rates.\n\n"
        "Open to a 15-minute conversation?\n\n"
        "Best,\n{sender_name}"
    ),
    "seasonal": (
        "Heading into peak leasing with {company}",
        "Hi {first_name},\n\n"
        "With peak leasing season here, inbound volume at {company} is likely climbing. Most "
        "teams we talk to say the bottleneck isn't demand — it's replying fast enough to keep "
        "prospective residents engaged.\n\n"
        "EliseAI handles the first touch on every inquiry: SMS, email, chat, follow-ups, and "
        "tour scheduling. It's worth a quick conversation before the season really spikes.\n\n"
        "Any time this week?\n\n"
        "Best,\n{sender_name}"
    ),
    "generic": (
        "Quick question on leasing at {company}",
        "Hi {first_name},\n\n"
        "Reaching out because {company} is exactly the kind of team we work with — operators "
        "managing properties where first-response time drives the lease.\n\n"
        "EliseAI is an AI leasing assistant that handles every inbound inquiry instantly — "
        "pricing, availability, tour scheduling — across SMS, email, and chat. Teams tend to "
        "see faster lead-to-tour conversion without adding leasing headcount.\n\n"
        "Worth 15 minutes to see if it's a fit?\n\n"
        "Best,\n{sender_name}"
    ),
}
