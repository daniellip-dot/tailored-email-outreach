"""Companies House signals: active directors + recent filing history."""
import os
import time
import itertools
import requests

CH_BASE = "https://api.company-information.service.gov.uk"

_keys = [os.getenv(f"CH_API_KEY_{i}") for i in range(1, 5)]
_keys = [k for k in _keys if k]
_key_cycle = itertools.cycle(_keys) if _keys else None

_last_call = [0.0]
MIN_INTERVAL = 0.5  # seconds between CH calls


def _throttle():
    elapsed = time.time() - _last_call[0]
    if elapsed < MIN_INTERVAL:
        time.sleep(MIN_INTERVAL - elapsed)
    _last_call[0] = time.time()


def _get(path):
    if not _key_cycle:
        raise RuntimeError("No CH_API_KEY_N set in environment")
    _throttle()
    key = next(_key_cycle)
    url = f"{CH_BASE}{path}"
    try:
        r = requests.get(url, auth=(key, ""), timeout=10)
        if r.status_code == 200:
            return r.json()
        return None
    except requests.RequestException:
        return None


def _normalise_name(raw):
    """'SMITH, John Michael' -> ('John', 'Smith').
    'John Smith' -> ('John', 'Smith')."""
    if not raw:
        return None, None
    raw = raw.strip()
    if "," in raw:
        surname, forenames = raw.split(",", 1)
        surname = surname.strip().title()
        forenames = forenames.strip()
        first = forenames.split()[0].title() if forenames else ""
        return first, surname
    parts = raw.split()
    if len(parts) == 1:
        return parts[0].title(), ""
    return parts[0].title(), parts[-1].title()


def get_active_director(company_number):
    """Return dict with first_name, last_name, full_name, appointed_on — or None."""
    data = _get(f"/company/{company_number}/officers?items_per_page=50")
    if not data:
        return None
    actives = []
    for o in data.get("items", []):
        if o.get("resigned_on"):
            continue
        role = (o.get("officer_role") or "").lower()
        if "director" not in role:
            continue
        actives.append(o)
    if not actives:
        return None
    # Earliest appointed first — likely founder
    actives.sort(key=lambda o: o.get("appointed_on") or "9999-99-99")
    top = actives[0]
    first, last = _normalise_name(top.get("name"))
    if not first:
        return None
    full = f"{first} {last}".strip()
    return {
        "first_name": first,
        "last_name": last,
        "full_name": full,
        "appointed_on": top.get("appointed_on"),
    }


def get_company_profile(company_number):
    data = _get(f"/company/{company_number}")
    if not data:
        return {}
    return {
        "incorporation_date": data.get("date_of_creation"),
        "company_status": data.get("company_status"),
        "accounts_category": (data.get("accounts") or {}).get("last_accounts", {}).get("type"),
    }


def get_filing_events(company_number, years=5):
    """Pull recent filings and summarise events relevant to outreach."""
    data = _get(f"/company/{company_number}/filing-history?items_per_page=50")
    if not data:
        return []
    from datetime import datetime, timedelta
    cutoff = datetime.utcnow() - timedelta(days=365 * years)
    events = []
    for item in data.get("items", []):
        dstr = item.get("date")
        try:
            d = datetime.strptime(dstr, "%Y-%m-%d") if dstr else None
        except Exception:
            d = None
        if d and d < cutoff:
            continue
        category = item.get("category", "")
        desc = item.get("description", "")
        if category in ("mortgage", "officers", "accounts", "capital", "incorporation", "resolution"):
            events.append({
                "date": dstr,
                "category": category,
                "description": desc,
            })
    return events[:20]
