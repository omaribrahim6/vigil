"""Claude classifier + briefing-memo author + action-items author.

Three responsibilities:

1. `classify_articles` — label Tavily news hits CRITICAL / HIGH / MEDIUM / NOISE.
2. `author_briefing_memo` — 4-sentence Minister-ready brief.
3. `author_actions` — prescriptive action items ('what should the funder do').

Backed by either:
- AWS Bedrock (`AWS_BEARER_TOKEN_BEDROCK` set) — preferred for the hackathon;
- Direct Anthropic API (`ANTHROPIC_API_KEY` set) — fallback;
- Deterministic keyword/rule-based fallback if neither is configured.

The fallback path keeps the demo running end-to-end even without an LLM."""
from __future__ import annotations

import json
import logging
import os
from typing import Any

from anthropic import Anthropic, AnthropicBedrock

from .config import SETTINGS
from .models import (
    ActionItem,
    ForensicSignals,
    NewsArticle,
    OrgProfile,
    RemediationContext,
    SanctionsHit,
    CourtCase,
)

logger = logging.getLogger(__name__)

CLASSIFY_SYSTEM = """You classify news articles for adverse-media screening of
organizations that receive Canadian government funding. Distinguish genuine
red flags (fraud charges, criminal investigations, sanctions, regulatory
enforcement actions, safety incidents, court findings) from noise (political
controversy, critical op-eds, opinion pieces, unrelated mentions) AND from
remediation signals (settlements completed, leadership turnover that
addressed past issues, deferred-prosecution agreements concluded, integrity
awards/certifications, monitorship concluded, rebrands tied to compliance
reform, new ethics programs).

For each article return:
- classification: CRITICAL | HIGH | MEDIUM | NOISE
- category: fraud | sanctions | criminal_charges | regulatory | safety |
            political_opinion | business_news | unrelated | remediation
- event_date: YYYY-MM-DD or null
- allegation_summary: one sentence describing the alleged red flag (or, for
                      remediation, the positive action taken)
- source_credibility: high | medium | low
- confidence: 0.0 to 1.0
- is_remediation: true if the article describes a positive integrity action
                  the entity has taken (e.g. completed DPA, paid settlement,
                  fired implicated leadership, won integrity award, certified
                  to ISO 37001 / Canadian government Integrity Regime, etc.).
                  Articles describing the *original wrongdoing* are NOT
                  remediation, even if remediation is mentioned in passing.

Precision over recall. When in doubt, classify as NOISE."""


BRIEFING_SYSTEM = """You write Minister-ready briefing memos. Tone: factual,
crisp, government-grade, no political colouring. Use exactly 4 sentences.

Sentence 1: Identify the entity and total federal funding to date.
Sentence 2: State the highest-severity adverse signal, citing the source AND
            the date / how recent it is. Distinguish current-state signals
            (active sanctions, ongoing investigations) from historic ones
            (>5 years old, since-remediated).
Sentence 3: If material remediation is documented (settlement completed, new
            leadership, monitorship concluded, integrity certification),
            state it. Otherwise, add at most one supporting forensic or
            court signal.
Sentence 4: State the recommendation, calibrated to the recency + remediation
            picture. A 7-year-old conviction with a completed DPA and new
            leadership is NOT the same risk as a current criminal charge."""


def _client() -> Anthropic | AnthropicBedrock | None:
    """Pick the best available Claude client. Bedrock if the hackathon-provided
    bearer token is set; else direct Anthropic; else None (fallback path)."""
    if SETTINGS.has_bedrock:
        if not os.environ.get("AWS_BEARER_TOKEN_BEDROCK"):
            os.environ["AWS_BEARER_TOKEN_BEDROCK"] = SETTINGS.aws_bearer_token_bedrock or ""
        if not os.environ.get("AWS_REGION"):
            os.environ["AWS_REGION"] = SETTINGS.aws_region
        try:
            return AnthropicBedrock(aws_region=SETTINGS.aws_region)
        except Exception as e:  # noqa: BLE001
            logger.warning("Bedrock client init failed (%s); falling back.", e)
    if SETTINGS.has_anthropic_direct:
        return Anthropic(api_key=SETTINGS.anthropic_api_key)
    return None


def _model_id() -> str:
    return SETTINGS.bedrock_model_id if SETTINGS.has_bedrock else SETTINGS.anthropic_model


REMEDIATION_KEYWORDS = [
    "deferred prosecution agreement", "remediation agreement",
    "settlement reached", "settled with", "paid the penalty",
    "monitorship concluded", "monitorship completed", "monitor lifted",
    "integrity award", "ethics certification", "iso 37001",
    "compliance certified", "new ceo", "new chief executive",
    "fired", "terminated", "leadership change", "removed from",
    "code of conduct", "ethics program", "compliance program",
    "rebranded as", "renamed to", "rebrand",
    "voluntary disclosure", "self-disclosed", "cleared by",
    "exonerated", "charges withdrawn", "charges dropped",
    "culture change",
]


def _fallback_classify(articles: list[NewsArticle], name: str = "") -> list[NewsArticle]:
    """Keyword-based degraded classifier for when Anthropic isn't configured.

    Tiers ordered most-severe first; first match wins. Matched against a
    lower-cased concatenation of title + summary. We also require the org
    name (or a meaningful prefix of it) to appear in the article text — most
    Tavily noise is generic 'Fraud Policy' PDFs that don't mention the org."""
    name_l = (name or "").strip().lower()
    name_tokens: list[str] = []
    if name_l:
        for token in name_l.replace("&", "and").split():
            t = token.strip(",.;:'\"()")
            if len(t) >= 4 and t not in {"the", "and", "ltd", "inc.", "inc", "corporation"}:
                name_tokens.append(t)
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
        # Demote articles that don't actually mention the org. (Most Tavily
        # noise is generic policy/explainer PDFs whose titles match adverse
        # keywords but never name the entity we're screening.)
        mentions_org = (
            not name_tokens or
            (name_l and name_l in text) or
            sum(1 for t in name_tokens if t in text) >= max(1, len(name_tokens) // 2)
        )
        sev = "NOISE"
        is_rem = a.is_remediation or any(k in text for k in REMEDIATION_KEYWORDS)
        if mentions_org and not is_rem:
            for tier in ("CRITICAL", "HIGH", "MEDIUM"):
                if any(k in text for k in keywords[tier]):
                    sev = tier
                    break
        category = "remediation" if is_rem else "auto"
        out.append(a.model_copy(update={
            "severity": sev,
            "category": category,
            "is_remediation": is_rem,
        }))
    return out


async def classify_articles(name: str, articles: list[NewsArticle]) -> list[NewsArticle]:
    if not articles:
        return []
    client = _client()
    if client is None:
        return _fallback_classify(articles, name=name)

    payload = [
        {
            "index": i,
            "title": a.title,
            "url": a.url,
            "source": a.source_name,
            "content": (a.summary or "")[:1500],
            "from_remediation_query": a.is_remediation,
        }
        for i, a in enumerate(articles)
    ]
    user = (
        f"Entity: {name}\n\n"
        f"Articles to classify (JSON):\n{json.dumps(payload, ensure_ascii=False)}\n\n"
        "Return ONLY a JSON array; one object per article in the same order, with keys: "
        "index, classification, category, event_date, allegation_summary, "
        "source_credibility, confidence, is_remediation.\n\n"
        "For event_date: extract the date the alleged event/decision occurred from "
        "the article body. Use YYYY-MM-DD. If multiple dates are present, use the "
        "primary event date (when the action took place). The URL may contain a "
        "date too (e.g. /2024/11/title or /article-name-2024). Use null only if "
        "no date can be reasonably inferred.\n\n"
        "For is_remediation: true ONLY when the article documents a corrective "
        "action the entity has TAKEN (settlement paid, leadership change to "
        "address compliance, monitorship concluded, integrity award won, ethics "
        "certification, charges dropped/withdrawn after compliance). Articles "
        "describing the original wrongdoing — even when remediation is mentioned "
        "in passing — are NOT remediation. The `from_remediation_query` field "
        "tells you the article came from a remediation-keyword query but you "
        "must still verify the content."
    )
    try:
        msg = client.messages.create(
            model=_model_id(),
            max_tokens=3000,
            system=CLASSIFY_SYSTEM,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")
        labels = _extract_json_array(text)
    except Exception as e:  # noqa: BLE001
        logger.warning("Claude classify failed: %s — falling back to keywords", e)
        return _fallback_classify(articles, name=name)

    from datetime import date as _date, datetime as _dt

    def _parse_iso(s: Any) -> _date | None:
        if not isinstance(s, str) or len(s) < 10:
            return None
        try:
            return _dt.fromisoformat(s[:10]).date()
        except ValueError:
            return None

    out: list[NewsArticle] = []
    for i, a in enumerate(articles):
        match = next((l for l in labels if l.get("index") == i), None)
        if not match:
            out.append(a.model_copy(update={
                "severity": "NOISE",
                "category": "unrated",
            }))
            continue
        event_date = _parse_iso(match.get("event_date"))
        is_rem = bool(match.get("is_remediation"))
        # If Claude flags it as remediation, the historic-adverse severity
        # shouldn't drive the risk score. We keep `severity` as classified
        # (it still describes the underlying event severity) but the risk
        # scorer ignores remediation-flagged articles.
        sev = match.get("classification") or "NOISE"
        cat = match.get("category") or "unrated"
        if is_rem and cat == "unrated":
            cat = "remediation"
        out.append(
            a.model_copy(
                update={
                    "severity": sev,
                    "category": cat,
                    "summary": match.get("allegation_summary") or a.summary,
                    "published_at": a.published_at or event_date,
                    "confidence": (
                        float(match["confidence"])
                        if isinstance(match.get("confidence"), (int, float))
                        else a.confidence
                    ),
                    "is_remediation": is_rem,
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
    remediation: RemediationContext | None = None,
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
        "top_adverse_news": [
            {
                "title": a.title,
                "severity": a.severity,
                "category": a.category,
                "summary": a.summary,
                "source": a.source_name,
                "date": a.published_at.isoformat() if a.published_at else None,
                "age_years": a.age_years,
                "is_stale": a.is_stale,
            }
            for a in news[:6] if not a.is_remediation
        ],
        "remediation": (
            {
                "signal_count": remediation.signal_count,
                "recent_signal_count": remediation.recent_signal_count,
                "most_recent_at": (
                    remediation.most_recent_at.isoformat()
                    if remediation.most_recent_at else None
                ),
                "summary": remediation.summary,
                "articles": [
                    {
                        "title": a.title,
                        "source": a.source_name,
                        "date": a.published_at.isoformat() if a.published_at else None,
                        "summary": a.summary,
                    }
                    for a in remediation.articles[:5]
                ],
            }
            if remediation else None
        ),
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
            model=_model_id(),
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


# ─── Action items (the prescriptive 'what should the funder do') ──────────

ACTIONS_SYSTEM = """You write prescriptive next-steps for a Canadian
government grant officer who has just been shown an adverse-screening dossier.

Output ONLY a JSON array of 2 to 5 action objects. Each object has:
- urgency: "immediate" | "scheduled" | "monitor" | "none"
- title: a short imperative sentence (e.g. "Pause next disbursement",
         "Refer to RCMP Anti-Corruption Unit", "Open Integrity Regime review")
- rationale: one sentence explaining why, citing the specific signal
- evidence: array of short labels for the supporting facts (e.g.
            "AG report 2024", "OpenSanctions hit", "T3010 violations")

Calibration — adverse signals:
- "immediate" only when there is an ACTIVE sanctions hit, recent (≤2y)
  criminal charge, current ban, recent registration revocation, or other
  already-confirmed adverse outcome that is still in-effect today.
- "scheduled" for serious-but-not-yet-confirmed signals (active investigation,
  AG findings, multiple HIGH news, large circular-gifting score).
- "monitor" for borderline / weak signals (mixed news, single forensic hit).
- "none" when no concerning signals were detected.

Calibration — remediation matters:
- If material remediation has occurred (settlement paid in full, monitorship
  concluded, leadership change addressed, integrity certification, charges
  withdrawn), DOWNGRADE the urgency by one level — historic adverse signals
  that have been demonstrably addressed should not warrant immediate action.
- The remediation section of the dossier tells you what corrective steps the
  org has taken. Reference them by name in your rationale when downgrading.
- A historic conviction (>5y old) with no documented remediation is still
  worth scheduling enhanced due diligence; you don't get to ignore it.
- An active sanctions hit is current state — never downgrade past "immediate"
  even if remediation is documented elsewhere.

Tone: factual, government-grade, no political colouring."""


def _fallback_actions(
    profile: OrgProfile,
    sanctions: list[SanctionsHit],
    court: list[CourtCase],
    news: list[NewsArticle],
    forensics: ForensicSignals,
    risk_score: int,
) -> list[ActionItem]:
    """Rule-based action-items used when no LLM is configured."""
    actions: list[ActionItem] = []
    has_critical_news = any(a.severity == "CRITICAL" for a in news)
    has_high_news = any(a.severity == "HIGH" for a in news)
    if sanctions:
        actions.append(
            ActionItem(
                urgency="immediate",
                title="Pause all disbursements pending sanctions review",
                rationale=f"OpenSanctions hit on '{sanctions[0].list_name}' (score {sanctions[0].score:.2f}); funding to a sanctioned entity may itself be a breach.",
                evidence=[f"OpenSanctions: {sanctions[0].list_name}"],
            )
        )
    if court:
        actions.append(
            ActionItem(
                urgency="scheduled",
                title="Cross-reference court matters with grant program eligibility",
                rationale=f"{len(court)} CanLII court decision(s) returned for this entity — confirm none are disqualifying under program terms.",
                evidence=[c.citation for c in court[:3]],
            )
        )
    if has_critical_news:
        crit = next(a for a in news if a.severity == "CRITICAL")
        actions.append(
            ActionItem(
                urgency="immediate",
                title="Trigger formal due-diligence review before next payment",
                rationale=f"Critical adverse media: \u201c{crit.title}\u201d ({crit.source_name}).",
                evidence=[crit.url] if crit.url else [crit.title],
            )
        )
    elif has_high_news:
        sample = next(a for a in news if a.severity == "HIGH")
        actions.append(
            ActionItem(
                urgency="scheduled",
                title="Open enhanced due-diligence file",
                rationale=f"Multiple HIGH-severity adverse-media hits, including: \u201c{sample.title}\u201d.",
                evidence=[sample.url] if sample.url else [sample.title],
            )
        )
    if forensics.cra_loop_score and forensics.cra_loop_score >= 15:
        actions.append(
            ActionItem(
                urgency="scheduled",
                title="Refer to CRA Charities Directorate for circular-gifting review",
                rationale=f"Pre-computed circular-gifting risk score is {forensics.cra_loop_score}/30 (Tarjan SCC + multi-hop cycle detection).",
                evidence=["cra.loop_universe"],
            )
        )
    if forensics.cra_t3010_violation_count and forensics.cra_t3010_violation_count >= 5:
        actions.append(
            ActionItem(
                urgency="monitor",
                title="Flag for CRA T3010 compliance follow-up",
                rationale=f"{forensics.cra_t3010_violation_count} T3010 form-arithmetic violations on file.",
                evidence=(forensics.cra_t3010_violation_examples or [])[:3] or ["cra.t3010_impossibilities"],
            )
        )
    if forensics.ab_sole_source_count and forensics.ab_sole_source_count >= 5:
        amt = forensics.ab_sole_source_value or 0
        actions.append(
            ActionItem(
                urgency="monitor",
                title="Review Alberta sole-source contracting pattern",
                rationale=f"{forensics.ab_sole_source_count} non-competitive Alberta contracts on file (~${amt:,.0f}).",
                evidence=["ab.ab_sole_source"],
            )
        )
    if not actions:
        if risk_score < 20:
            actions.append(
                ActionItem(
                    urgency="none",
                    title="No concerning signals detected — clear for funding decision",
                    rationale="External sanctions, court, news, and forensic-signal sweeps returned no critical or high indicators.",
                    evidence=["full sweep clean"],
                )
            )
        else:
            actions.append(
                ActionItem(
                    urgency="monitor",
                    title="Add to enhanced-monitoring watchlist",
                    rationale="Mixed signals returned but none rise to the immediate-action threshold.",
                    evidence=["risk_score=" + str(risk_score)],
                )
            )
    return actions[:5]


async def author_actions(
    profile: OrgProfile,
    sanctions: list[SanctionsHit],
    court: list[CourtCase],
    news: list[NewsArticle],
    forensics: ForensicSignals,
    risk_score: int,
    remediation: RemediationContext | None = None,
) -> list[ActionItem]:
    client = _client()
    if client is None:
        return _fallback_actions(profile, sanctions, court, news, forensics, risk_score)
    adverse_news = [a for a in news if not a.is_remediation]
    context = {
        "name": profile.canonical_name,
        "fed_total": profile.fed_total,
        "ab_total": profile.ab_total,
        "risk_score": risk_score,
        "sanctions_hits": len(sanctions),
        "sanctions_summary": [
            {"list": s.list_name, "score": s.score} for s in sanctions[:3]
        ],
        "court_case_count": len(court),
        "court_summary": [{"citation": c.citation, "title": c.title} for c in court[:3]],
        "news_severity_counts": {
            "CRITICAL": sum(1 for a in adverse_news if a.severity == "CRITICAL"),
            "HIGH": sum(1 for a in adverse_news if a.severity == "HIGH"),
            "MEDIUM": sum(1 for a in adverse_news if a.severity == "MEDIUM"),
        },
        "top_adverse_news": [
            {
                "title": a.title,
                "severity": a.severity,
                "source": a.source_name,
                "date": a.published_at.isoformat() if a.published_at else None,
                "age_years": a.age_years,
                "is_stale": a.is_stale,
            }
            for a in adverse_news[:5] if a.severity in ("CRITICAL", "HIGH")
        ],
        "remediation": (
            {
                "signal_count": remediation.signal_count,
                "recent_signal_count": remediation.recent_signal_count,
                "most_recent_at": (
                    remediation.most_recent_at.isoformat()
                    if remediation.most_recent_at else None
                ),
                "summary": remediation.summary,
                "articles": [
                    {
                        "title": a.title,
                        "source": a.source_name,
                        "date": a.published_at.isoformat() if a.published_at else None,
                    }
                    for a in remediation.articles[:5]
                ],
            }
            if remediation else None
        ),
        "forensics": {
            "circular_gifting_score": forensics.cra_loop_score,
            "circular_gifting_max": 30,
            "t3010_violations": forensics.cra_t3010_violation_count,
            "ab_sole_source_count": forensics.ab_sole_source_count,
            "max_overhead_ratio": forensics.cra_max_overhead_ratio,
        },
    }
    user = (
        "Produce JSON action items for this dossier:\n"
        f"{json.dumps(context, ensure_ascii=False, default=str)}\n\n"
        "Return ONLY the JSON array."
    )
    try:
        msg = client.messages.create(
            model=_model_id(),
            max_tokens=1200,
            system=ACTIONS_SYSTEM,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")
        raw = _extract_json_array(text)
        out: list[ActionItem] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            try:
                out.append(
                    ActionItem(
                        urgency=item.get("urgency", "monitor"),
                        title=str(item.get("title", "")).strip()[:200],
                        rationale=str(item.get("rationale", "")).strip()[:400],
                        evidence=[str(e) for e in (item.get("evidence") or [])][:5],
                    )
                )
            except Exception:  # noqa: BLE001
                continue
        if out:
            return out[:5]
    except Exception as e:  # noqa: BLE001
        logger.warning("Claude actions failed: %s", e)
    return _fallback_actions(profile, sanctions, court, news, forensics, risk_score)
