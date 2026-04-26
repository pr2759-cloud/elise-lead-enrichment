"""Timing category: trigger events, news velocity, seasonality."""
from __future__ import annotations

from ..config import CATEGORY_WEIGHTS, NEUTRAL_SUBSIGNAL_SCORE
from ..models import CategoryScore, NewsEnrichment
from ..heuristics.seasonality import seasonality_score


def _trigger_event_score(news: NewsEnrichment) -> float:
    if news.trigger_headline_30d:
        return 10.0
    if news.trigger_headline_90d:
        return 7.0
    if news.articles_90d > 0:
        return 5.0
    return 2.0


def _news_velocity_score(news: NewsEnrichment) -> float:
    if news.articles_30d >= 3:
        return 10.0
    if news.articles_30d >= 1:
        return 7.0
    if news.articles_90d >= 1:
        return 5.0
    return 2.0


def score_timing(news: NewsEnrichment) -> CategoryScore:
    cat = CategoryScore(name="timing", weight=CATEGORY_WEIGHTS["timing"])

    # Trigger Event
    if news.error is None:
        cat.sub_signals["trigger_event"] = _trigger_event_score(news)
    else:
        cat.sub_signals["trigger_event"] = NEUTRAL_SUBSIGNAL_SCORE
        cat.missing.append("trigger_event")

    # News Velocity
    if news.error is None:
        cat.sub_signals["news_velocity"] = _news_velocity_score(news)
    else:
        cat.sub_signals["news_velocity"] = NEUTRAL_SUBSIGNAL_SCORE
        cat.missing.append("news_velocity")

    # Seasonality (always available — runs off the wall clock)
    cat.sub_signals["seasonality"] = seasonality_score()

    return cat
