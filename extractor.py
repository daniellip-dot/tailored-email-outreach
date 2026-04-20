"""Claude Haiku hook extraction."""
import os
import json
import re
from anthropic import Anthropic

MODEL = "claude-haiku-4-5-20251001"

PROMPT_TEMPLATE = """You are a research analyst for a UK private equity firm doing pre-outreach \
research on acquisition targets. You are finding ONE specific, verifiable hook for a \
personalised cold email.

COMPANY: {company_name}
DIRECTOR: {director_full_name}
SECTOR: {sic_description}
LOCATION: {postcode}
INCORPORATION DATE: {incorporation_date}

WEBSITE CONTENT (truncated):
{website_text}

WEBSITE SIGNALS:
Years mentioned: {years}
Accreditations: {accreditations}

COMPANIES HOUSE RECENT EVENTS:
{ch_events}

NEWS HEADLINES (last 24 months):
{news_headlines}

YOUR JOB:
Find ONE specific, verifiable hook for a personalised cold email opener.

RULES:
- Must be factually supported by the input data - no speculation
- Must be SPECIFIC (a date, number, name, event, accreditation, contract) \
- not generic flattery
- Must be something 95% of the director's competitors could NOT claim
- Must be positive or neutral - no "I noticed your revenue decline"
- UK English, under 20 words
- The hook should prove research, not flatter

GOOD EXAMPLES:
- "BAFE SP203-1 since 2007 - one of the longest-standing in Kent"
- "Incorporated 1978 - most independents in this sector were bought out by Marlowe years ago"
- "Noticed you registered a new charge with NatWest last month"
- "Third engineer hired in 2024 per your website - clear growth push"

BAD EXAMPLES:
- "Impressive growth trajectory" (generic)
- "Your commitment to safety" (every firm in this sector says this)
- "Market leader" (meaningless)

Return ONLY valid JSON (no other text, no markdown code fences):
{{
  "hook": "<one sentence under 20 words>",
  "source": "<website|ch|news|multiple>",
  "confidence": "high|medium|low",
  "suggested_opener": "<full opening sentence for the email, using the hook naturally>",
  "research_notes": "<2-3 sentences explaining what you found and why you chose this hook>"
}}

If no genuine specific hook can be found:
{{
  "hook": null,
  "confidence": "none",
  "research_notes": "<why - e.g. 'website is a template with no specific claims, no CH events of note, no news coverage'>"
}}
"""


def _client():
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    return Anthropic(api_key=key)


def _format_ch_events(events):
    if not events:
        return "(none)"
    lines = []
    for e in events[:10]:
        lines.append(f"- {e.get('date','?')} [{e.get('category','?')}] {e.get('description','')}")
    return "\n".join(lines)


def _format_news(items):
    if not items:
        return "(none)"
    lines = []
    for n in items[:8]:
        lines.append(f"- {n.get('date','?')}: {n.get('title','')} — {n.get('snippet','')}")
    return "\n".join(lines)


def _extract_json(text):
    """Best-effort extract JSON from model output."""
    text = text.strip()
    # Strip common markdown fences
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    return None


def extract_hook(company_name, director_full_name, sic_description, postcode,
                 incorporation_date, website_data, ch_events, news_items):
    """Call Haiku. Returns (parsed_dict, raw_response_text)."""
    website_text = (website_data or {}).get("text", "") or "(no website content)"
    years = ", ".join((website_data or {}).get("years", [])) or "(none)"
    accreds = ", ".join((website_data or {}).get("accreditations", [])) or "(none)"

    prompt = PROMPT_TEMPLATE.format(
        company_name=company_name or "",
        director_full_name=director_full_name or "(unknown)",
        sic_description=sic_description or "",
        postcode=postcode or "",
        incorporation_date=incorporation_date or "(unknown)",
        website_text=website_text,
        years=years,
        accreditations=accreds,
        ch_events=_format_ch_events(ch_events),
        news_headlines=_format_news(news_items),
    )

    client = _client()
    msg = client.messages.create(
        model=MODEL,
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = msg.content[0].text if msg.content else ""
    parsed = _extract_json(raw) or {
        "hook": None,
        "confidence": "none",
        "research_notes": "Parser failed to read LLM response.",
    }
    return parsed, raw
