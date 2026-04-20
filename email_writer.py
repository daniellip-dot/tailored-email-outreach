"""Generate subject + body from template + hook data."""
import os
import time
import requests

TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "templates", "fire_safety_direct.md")

_postcode_cache = {}
_last_pc_call = [0.0]


def _lookup_town(postcode):
    if not postcode:
        return None
    pc = postcode.strip().upper()
    if pc in _postcode_cache:
        return _postcode_cache[pc]
    elapsed = time.time() - _last_pc_call[0]
    if elapsed < 0.3:
        time.sleep(0.3 - elapsed)
    _last_pc_call[0] = time.time()
    try:
        r = requests.get(f"https://api.postcodes.io/postcodes/{pc}", timeout=5)
        if r.status_code == 200:
            res = r.json().get("result", {}) or {}
            town = res.get("post_town") or res.get("admin_district") or res.get("parish")
            if town:
                town = town.title()
                _postcode_cache[pc] = town
                return town
    except requests.RequestException:
        pass
    _postcode_cache[pc] = None
    return None


def _sector_description(sic_description):
    if not sic_description:
        return "owner-run"
    s = sic_description.lower()
    if "fire" in s:
        return "fire safety"
    if "vehicle" in s or "garage" in s:
        return "motor garage"
    if "nurs" in s or "pre-primary" in s:
        return "children's nursery"
    words = sic_description.split()
    return " ".join(words[:4])


def _build_subject(hook_source, company_name, first_name, sic_description, town):
    if hook_source == "location" and town:
        return f"Buying {_sector_description(sic_description)} businesses in {town}"
    if hook_source in ("website", "ch", "news", "multiple") and company_name:
        return f"{company_name} — quick note from a buyer"
    return f"Quick question, {first_name}" if first_name else "Quick question"


def _load_template():
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        return f.read()


def generate_email(first_name, hook_result, company_name, sic_description, postcode):
    """Return dict with subject, body, opener — or None values if no hook."""
    if not hook_result or not hook_result.get("hook"):
        return {
            "subject": "",
            "body": "SKIP_NO_HOOK",
            "opener": "",
        }

    opener = hook_result.get("suggested_opener") or hook_result.get("hook") or ""
    source = hook_result.get("source", "")
    town = _lookup_town(postcode)

    subject = _build_subject(source, company_name, first_name, sic_description, town)

    template = _load_template()
    # Template first line is "Subject: {subject}" — strip it, we return subject separately
    lines = template.splitlines()
    if lines and lines[0].lower().startswith("subject:"):
        body_template = "\n".join(lines[1:]).lstrip("\n")
    else:
        body_template = template

    body = body_template.format(
        first_name=first_name or "there",
        opener=opener,
        sender_name=os.getenv("SENDER_NAME", "Daniel"),
        sender_mobile=os.getenv("SENDER_MOBILE", ""),
        sender_company=os.getenv("SENDER_COMPANY", "V Squared Partners"),
        sector_description=_sector_description(sic_description),
    )

    return {
        "subject": subject,
        "body": body,
        "opener": opener,
    }
