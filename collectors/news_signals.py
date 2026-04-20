"""News signals via Serper /news endpoint."""
import os
import time
import requests
from datetime import datetime, timedelta

SERPER_URL = "https://google.serper.dev/news"
_last_call = [0.0]
MIN_INTERVAL = 1.0  # 1s between Serper calls


def _throttle():
    elapsed = time.time() - _last_call[0]
    if elapsed < MIN_INTERVAL:
        time.sleep(MIN_INTERVAL - elapsed)
    _last_call[0] = time.time()


def _query(q, num=5):
    key = os.getenv("SERPER_API_KEY")
    if not key:
        return []
    _throttle()
    try:
        r = requests.post(
            SERPER_URL,
            headers={"X-API-KEY": key, "Content-Type": "application/json"},
            json={"q": q, "gl": "gb", "num": num},
            timeout=10,
        )
        if r.status_code != 200:
            return []
        return r.json().get("news", []) or []
    except requests.RequestException:
        return []


def _parse_date(s):
    """Serper returns relative strings like '2 days ago' or dates. Return ISO or None."""
    if not s:
        return None
    s = s.strip().lower()
    try:
        if "day" in s:
            n = int(s.split()[0])
            return (datetime.utcnow() - timedelta(days=n)).date().isoformat()
        if "week" in s:
            n = int(s.split()[0])
            return (datetime.utcnow() - timedelta(weeks=n)).date().isoformat()
        if "month" in s:
            n = int(s.split()[0])
            return (datetime.utcnow() - timedelta(days=30 * n)).date().isoformat()
        if "year" in s:
            n = int(s.split()[0])
            return (datetime.utcnow() - timedelta(days=365 * n)).date().isoformat()
        if "hour" in s or "minute" in s:
            return datetime.utcnow().date().isoformat()
    except (ValueError, IndexError):
        pass
    return None


def _within_24_months(date_iso):
    if not date_iso:
        return True  # keep if unknown
    try:
        d = datetime.strptime(date_iso, "%Y-%m-%d")
    except ValueError:
        return True
    return d > datetime.utcnow() - timedelta(days=730)


def search(company_name, director_full_name=None):
    """Return up to 8 recent news items with title, snippet, date."""
    results = []
    seen_titles = set()

    for item in _query(f'"{company_name}"', num=5):
        title = item.get("title", "")
        if title in seen_titles:
            continue
        seen_titles.add(title)
        date_iso = _parse_date(item.get("date"))
        if not _within_24_months(date_iso):
            continue
        results.append({
            "title": title,
            "snippet": item.get("snippet", ""),
            "date": date_iso or item.get("date", ""),
        })

    if director_full_name:
        for item in _query(f'"{director_full_name}" "{company_name}"', num=3):
            title = item.get("title", "")
            if title in seen_titles:
                continue
            seen_titles.add(title)
            date_iso = _parse_date(item.get("date"))
            if not _within_24_months(date_iso):
                continue
            results.append({
                "title": title,
                "snippet": item.get("snippet", ""),
                "date": date_iso or item.get("date", ""),
            })

    return results
