# tailored-email-outreach

Takes a CSV of UK companies (output from `domain-finder`) and produces personalised cold email drafts — one per company — using Companies House signals, website scraping, news search, and Claude Haiku for hook extraction.

## What it does (plain English)

For each company in your input CSV:

1. Looks up the active director on Companies House
2. Scrapes their website (about/news/team/contact pages)
3. Pulls recent CH filing history (incorporations, charges, appointments)
4. Searches Google News for recent mentions of the company and director
5. Sends all signals to Claude Haiku, which extracts **one** specific, verifiable hook
6. Generates a subject line + full email body ready to send

Output is an enriched CSV with director name, hook, subject, body, confidence score, and research notes for human review.

## Install

```bash
git clone https://github.com/daniellip-dot/tailored-email-outreach.git
cd tailored-email-outreach
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# then edit .env with your API keys
```

## Required API keys (all go in `.env`)

- `CH_API_KEY_1..4` — Companies House (free, 4 keys recommended for rate limit headroom)
- `SERPER_API_KEY` — google.serper.dev (cheap, pay-per-call)
- `ANTHROPIC_API_KEY` — console.anthropic.com (pay-per-call, ~£0.0008/company)

## Run

```bash
# Dry run: process first 5 rows, print to console, don't write DB
python3 tailored_outreach.py --input domains.csv --dry-run

# Full run
python3 tailored_outreach.py --input domains.csv --output drafts.csv

# Limit to first N companies
python3 tailored_outreach.py --input domains.csv --limit 50
```

## Input CSV columns (from domain-finder)

`company_number, company_name, domain, postcode, sic_description, confidence, method, phone, email_from_snippet`

## Output CSV columns (input + additions)

`director_first_name, director_last_name, director_full_name, hook, opener, subject, email_body, confidence_research, sources_used, research_notes`

If no strong hook can be found, `email_body` is set to `SKIP_NO_HOOK` — these rows should be routed to your generic/mass template instead of personalised outreach.

## Resume

Progress is saved to SQLite (`research.db`) after every row. Re-running with the same input skips anything already processed — safe to kill and restart.

## Cost

Roughly £0.001 per company (Haiku + Serper combined). 1,000 companies ≈ £1.

## Not included by design

No Docker, no web UI, no Flask, no scheduler. Pure CLI. Credentials via `.env` only.
