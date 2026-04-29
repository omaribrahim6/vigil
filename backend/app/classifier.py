"""Claude classifier + briefing-memo author.

Two responsibilities:

1. `classify_articles` — given Tavily news hits, ask Claude (one batched call)
   to label each as CRITICAL / HIGH / MEDIUM / NOISE with a category, summary,
   and confidence. Spec §6 step 5.
2. `author_briefing_memo` — given the assembled dossier (sanctions, court
   cases, classified articles, forensic signals, funding profile), ask Claude
   to write a 4-sentence Minister-ready brief. The "why flagged" panel.

If `ANTHROPIC_API_KEY` is missing, both functions return deterministic
fallbacks rather than failing — so the demo still runs end-to-end."""
from __future__ import annotations

import json
import logging
from typing import Any

from anthropic import Anthropic

from .config import SETTINGS
from .models import ForensicSignals, NewsArticle, OrgProfile, SanctionsHit, CourtCase

logger = logging.getLogger(__name__)

CLASSIFY_SYSTEM = """You classify news articles for adverse-media screening of
organizations that receive Canadian government funding. Distinguish genuine
red flags (fraud charges, criminal investigations, sanctions, regulatory
enforcement actions, safety incidents, court findings) from noise (political
controversy, critical op-eds, opinion pieces, unrelated mentions).

For each article return:
- classification: CRITICAL | HIGH | MEDIUM | NOISE
- category: fraud | sanctions | criminal_charges | regulatory | safety |
            political_opinion | business_news | unrelated
- event_date: YYYY-MM-DD or null
- allegation_summary: one sentence describing the alleged red flag
- source_credibility: high | medium | low
- confidence: 0.0 to 1.0

Precision over recall. When in doubt, classify as NOISE."""


BRIEFING_SYSTEM = """You write Minister-ready briefing memos. Tone: factual,
crisp, government-grade, no political colouring. Use exactly 4 sentences.

Sentence 1: Identify the entity and total federal funding to date.
Sentence 2: State the highest-severity adverse signal, citing the source.
Sentence 3: Add at most one supporting forensic or court signal.
Sentence 4: State the recommendation (e.g., "elevated due-diligence review
recommended before next disbursement", "no concerning signals detected", or
similar). Reference uncertainty where it exists."""


def _client() -> Anthropic | None:
    if not SETTINGS.has_anthropic:
        return None
    return Anthropic(api_key=SETTINGS.anthropic_api_key)


def _fallback_classify(articles: list[NewsArticle]) -> list[NewsArticle]:
    """Keyword-based degraded classifier for when Anthropic isn't configured.

    Tiers ordered most-severe first; first match wins. Matched against a
    lower-cased concatenation of title + summary."""
    keywords: dict[str, list[str]] = {
        "CRITICAL": [
            "fraud charge", "fraud charges", "indicted", "indictment",
            "convicted", "guilty plea", "guilty of", "criminal charges",
            "embezzlement", "embezzled", "money laundering", "bribery",
            "sanctions imposed", "added to sanctions", "ofac",
            "registration revoked", "charity status revoked",
            "rcmp charges", "raid", "search warrant",
            "ineligible for federal", "barred from", "debarred",
            "court found", "found guilty",
        ],
        "HIGH": [
            "investigation", "rcmp investigation", "rcmp", "auditor general",
            "ag report", "ethics commissioner", "lawsuit", "sued", "litigation",
            "regulator", "revoked", "wound down", "cease and desist",
            "audit found", "improper", "misconduct", "conflict of interest",
            "whistleblower", "kickback", "non-competitive contract",
            "sole-source contract", "wrongdoing", "complaint filed",
            "settled", "settlement",
        ],
        "MEDIUM": [
            "scandal", "scandals", "controversy", "controversial", "scrutiny",
            "criticized", "criticism", "questioned", "ethics complaint",
            "withdrew", "withdrawn", "withdrew from", "dropped",
            "stepped down", "resigned", "fallout", "mishandled",
        ],
    }
    out: list[NewsArticle] = []
    for a in articles:
        text = f"{a.title or ''} {a.summary or ''}".lower()
        sev = "NOISE"
        for tier in ("CRITICAL", "HIGH", "MEDIUM"):
            if any(k in text for k in keywords[tier]):
                sev = tier
                break
        out.append(a.model_copy(update={"severity": sev, "category": "auto"}))
    return out


async def classify_articles(name: str, articles: list[NewsArticle]) -> list[NewsArticle]:
    if not articles:
        return []
    client = _client()
    if client is None:
        return _fallback_classify(articles)

    payload = [
        {"index": i, "title": a.title, "url": a.url, "summary": (a.summary or "")[:500]}
        for i, a in enumerate(articles)
    ]
    user = (
        f"Entity: {name}\n\n"
        f"Articles to classify (JSON):\n{json.dumps(payload, ensure_ascii=False)}\n\n"
        "Return ONLY a JSON array; one object per article in the same order, with keys: "
        "index, classification, category, event_date, allegation_summary, "
        "source_credibility, confidence."
    )
    try:
        msg = client.messages.create(
            model=SETTINGS.anthropic_model,
            max_tokens=2000,
            system=CLASSIFY_SYSTEM,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")
        labels = _extract_json_array(text)
    except Exception as e:  # noqa: BLE001
        logger.warning("Claude classify failed: %s — falling back to keywords", e)
        return _fallback_classify(articles)

    out: list[NewsArticle] = []
    for i, a in enumerate(articles):
        match = next((l for l in labels if l.get("index") == i), None)
        if not match:
            out.append(a.model_copy(update={"severity": "NOISE", "category": "unrated"}))
            continue
        out.append(
            a.model_copy(
                update={
                    "severity": match.get("classification") or "NOISE",
                    "category": match.get("category") or "unrated",
                    "summary": match.get("allegation_summary") or a.summary,
                    "confidence": (
                        float(match["confidence"])
                        if isinstance(match.get("confidence"), (int, float))
                        else a.confidence
                    ),
                }
            )
        )
    return out


def _extract_json_array(text: str) -> list[dict[str, Any]]:
    text = text.strip()
    if text.startswith("```"):
        lines = [l for l in text.splitlines() if not l.strip().startswith("```")]
        text = "\n".join(lines)
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1:
        return []
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _fallback_briefing(
    profile: OrgProfile,
    sanctions: list[SanctionsHit],
    court: list[CourtCase],
    news: list[NewsArticle],
    forensics: ForensicSignals,
) -> str:
    parts: list[str] = []
    fed_clause = (
        f"received approximately ${profile.fed_total:,.0f} in federal funding"
        if profile.fed_total else "appears in Canadian government funding records"
    )
    parts.append(f"{profile.canonical_name} ({profile.province or 'Canada'}) {fed_clause}.")
    if sanctions:
        s = sanctions[0]
        parts.append(
            f"Highest-severity signal: OpenSanctions hit on {s.list_name} (score {s.score:.2f})."
        )
    elif court:
        c = court[0]
        parts.append(
            f"Highest-severity signal: court matter {c.citation}"
            + (f" ({c.decision_date.isoformat()})" if c.decision_date else "")
            + "."
        )
    elif any((a.severity in ("CRITICAL", "HIGH")) for a in news):
        a = next(x for x in news if x.severity in ("CRITICAL", "HIGH"))
        parts.append(f"Highest-severity signal: media coverage \u2014 \u201c{a.title}\u201d ({a.source_name}).")
    else:
        parts.append("No critical adverse-media signals detected in current sweep.")
    if forensics.cra_loop_score and forensics.cra_loop_score >= 10:
        parts.append(
            f"Forensic note: pre-computed circular-gifting risk score "
            f"{forensics.cra_loop_score}/30 in CRA T3010 graph."
        )
    elif forensics.cra_t3010_violation_count and forensics.cra_t3010_violation_count > 0:
        parts.append(
            f"Forensic note: {forensics.cra_t3010_violation_count} T3010 form violations on file."
        )
    elif forensics.ab_sole_source_count and forensics.ab_sole_source_count > 0:
        parts.append(
            f"Forensic note: {forensics.ab_sole_source_count} non-competitive Alberta contracts."
        )
    else:
        parts.append("No supporting forensic-layer flags raised in this sweep.")
    if sanctions or court or any(a.severity in ("CRITICAL", "HIGH") for a in news):
        parts.append("Elevated due-diligence review recommended before any further disbursement.")
    else:
        parts.append("No further action required at this time.")
    return " ".join(parts[:4])


async def author_briefing_memo(
    profile: OrgProfile,
    sanctions: list[SanctionsHit],
    court: list[CourtCase],
    news: list[NewsArticle],
    forensics: ForensicSignals,
    risk_score: int,
) -> str:
    client = _client()
    if client is None:
        return _fallback_briefing(profile, sanctions, court, news, forensics)
    context = {
        "name": profile.canonical_name,
        "province": profile.province,
        "fed_total": profile.fed_total,
        "ab_total": profile.ab_total,
        "cra_designation": profile.cra_designation,
        "risk_score": risk_score,
        "sanctions": [
            {"list": s.list_name, "score": s.score, "countries": s.countries}
            for s in sanctions[:5]
        ],
        "court_cases": [
            {
                "citation": c.citation,
                "title": c.title,
                "date": c.decision_date.isoformat() if c.decision_date else None,
                "url": c.url,
            }
            for c in court[:5]
        ],
        "top_news": [
            {
                "title": a.title,
                "severity": a.severity,
                "category": a.category,
                "summary": a.summary,
                "source": a.source_name,
                "date": a.published_at.isoformat() if a.published_at else None,
            }
            for a in news[:6]
        ],
        "forensics": {
            "cra_loop_score": forensics.cra_loop_score,
            "cra_loop_score_max": 30,
            "t3010_violation_count": forensics.cra_t3010_violation_count,
            "max_overhead_ratio": forensics.cra_max_overhead_ratio,
            "ab_sole_source_count": forensics.ab_sole_source_count,
            "ab_sole_source_value": forensics.ab_sole_source_value,
            "shared_director_clusters": (
                len(forensics.shared_directors) if forensics.shared_directors else 0
            ),
        },
    }
    user = (
        "Write a 4-sentence Minister-ready briefing memo using the JSON dossier "
        "below. Cite specific numbers and source names. Do not include headers, "
        "bullet points, or prefixes like 'Briefing Memo:' \u2014 just the four "
        "sentences as a paragraph.\n\n"
        f"Dossier:\n{json.dumps(context, ensure_ascii=False, default=str)}"
    )
    try:
        msg = client.messages.create(
            model=SETTINGS.anthropic_model,
            max_tokens=500,
            system=BRIEFING_SYSTEM,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text").strip()
        if text:
            return text
    except Exception as e:  # noqa: BLE001
        logger.warning("Claude briefing failed: %s", e)
    return _fallback_briefing(profile, sanctions, court, news, forensics)
