"""Scrape a company website for text + signals. Free, best-effort."""
import re
import requests
from bs4 import BeautifulSoup

PATHS = ["/", "/about", "/about-us", "/our-story", "/news", "/team", "/our-team", "/contact"]

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; research bot)"}

ACCREDITATIONS = [
    "BAFE", "FIRAS", "NSI", "SSAIB", "ISO 9001", "FIA", "IFE",
    "Fire Industry Association",
]

YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
PHONE_RE = re.compile(r"(?:\+44\s?|0)(?:\d\s?){9,10}\d")


def _normalise_url(domain):
    domain = domain.strip().lower()
    if domain.startswith("http://") or domain.startswith("https://"):
        return domain.rstrip("/")
    return "https://" + domain.rstrip("/")


def _fetch(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=5, allow_redirects=True)
        if r.status_code == 200 and "text/html" in r.headers.get("Content-Type", ""):
            return r.text
    except requests.RequestException:
        return None
    return None


def _extract_text(html):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    return re.sub(r"\s+", " ", text)


def scrape(domain):
    """Returns dict with text (truncated), years, emails, phones, accreditations."""
    if not domain:
        return None
    base = _normalise_url(domain)
    collected = []
    pages_fetched = 0
    for path in PATHS:
        url = base + path if path != "/" else base
        html = _fetch(url)
        if not html:
            continue
        pages_fetched += 1
        txt = _extract_text(html)
        if txt:
            collected.append(txt)
        if len(" ".join(collected)) > 8000:
            break
    if not collected:
        return {
            "text": "",
            "years": [],
            "emails": [],
            "phones": [],
            "accreditations": [],
            "pages_fetched": 0,
        }
    combined = " ".join(collected)
    combined_trunc = combined[:4000]
    years = sorted(set(YEAR_RE.findall(combined)))
    emails = sorted(set(EMAIL_RE.findall(combined)))
    phones = sorted(set(PHONE_RE.findall(combined)))
    accreds = [a for a in ACCREDITATIONS if a.lower() in combined.lower()]
    return {
        "text": combined_trunc,
        "years": years,
        "emails": emails[:5],
        "phones": phones[:5],
        "accreditations": accreds,
        "pages_fetched": pages_fetched,
    }
