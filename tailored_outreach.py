#!/usr/bin/env python3
"""Tailored cold email outreach — main CLI.

Takes a CSV of companies (output from domain-finder) and produces personalised
cold email drafts using CH signals + website scrape + news + Claude Haiku.
"""
import argparse
import os
import sqlite3
import sys
import traceback
import pandas as pd
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()

from collectors import ch_signals, website_scrape, news_signals
import extractor
import email_writer

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")

OUTPUT_COLUMNS = [
    "company_number", "company_name", "domain", "postcode", "sic_description",
    "confidence", "method", "phone", "email_from_snippet",
    "director_first_name", "director_last_name", "director_full_name",
    "hook", "opener", "subject", "email_body",
    "confidence_research", "sources_used", "research_notes",
]


def open_db(path):
    conn = sqlite3.connect(path)
    with open(SCHEMA_PATH, "r") as f:
        conn.executescript(f.read())
    conn.commit()
    return conn


def already_processed(conn):
    cur = conn.execute("SELECT company_number FROM research")
    return {row[0] for row in cur.fetchall()}


def save_row(conn, row):
    conn.execute("""
        INSERT OR REPLACE INTO research (
            company_number, company_name, domain,
            director_first_name, director_last_name, director_full_name,
            hook, opener, subject, email_body,
            confidence_research, sources_used, research_notes,
            website_text_sample, raw_llm_response
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        row.get("company_number"), row.get("company_name"), row.get("domain"),
        row.get("director_first_name"), row.get("director_last_name"),
        row.get("director_full_name"),
        row.get("hook"), row.get("opener"), row.get("subject"), row.get("email_body"),
        row.get("confidence_research"), row.get("sources_used"),
        row.get("research_notes"),
        row.get("website_text_sample"), row.get("raw_llm_response"),
    ))
    conn.commit()


def process_one(row_in, counters):
    """Process one input row. Returns merged dict for CSV output."""
    out = dict(row_in)
    out.update({
        "director_first_name": "", "director_last_name": "", "director_full_name": "",
        "hook": "", "opener": "", "subject": "", "email_body": "",
        "confidence_research": "NONE", "sources_used": "", "research_notes": "",
        "website_text_sample": "", "raw_llm_response": "",
    })

    company_number = str(row_in.get("company_number", "")).strip()
    company_name = row_in.get("company_name", "")
    domain = row_in.get("domain") or ""
    postcode = row_in.get("postcode", "")
    sic_description = row_in.get("sic_description", "")
    inbound_confidence = (row_in.get("confidence") or "").upper()

    if not domain or inbound_confidence == "NONE":
        out["research_notes"] = "Skipped: no domain or confidence=NONE in input."
        return out

    sources = []

    # Director
    try:
        director = ch_signals.get_active_director(company_number)
        counters["ch_calls"] += 1
    except Exception as e:
        print(f"  [warn] CH director lookup failed: {e}", file=sys.stderr)
        director = None

    if not director:
        out["research_notes"] = "No active director found in Companies House."
        return out

    out["director_first_name"] = director["first_name"]
    out["director_last_name"] = director["last_name"]
    out["director_full_name"] = director["full_name"]
    sources.append("ch")

    # CH profile + filings
    try:
        profile = ch_signals.get_company_profile(company_number)
        counters["ch_calls"] += 1
    except Exception:
        profile = {}
    try:
        ch_events = ch_signals.get_filing_events(company_number)
        counters["ch_calls"] += 1
    except Exception:
        ch_events = []

    # Website
    try:
        site = website_scrape.scrape(domain)
        if site and site.get("text"):
            sources.append("website")
            out["website_text_sample"] = site["text"][:500]
    except Exception as e:
        print(f"  [warn] website scrape failed: {e}", file=sys.stderr)
        site = None

    # News
    try:
        news_items = news_signals.search(company_name, director["full_name"])
        counters["serper_calls"] += 2  # we issue up to 2 queries per company
        if news_items:
            sources.append("news")
    except Exception as e:
        print(f"  [warn] news search failed: {e}", file=sys.stderr)
        news_items = []

    # Hook extraction
    try:
        parsed, raw = extractor.extract_hook(
            company_name=company_name,
            director_full_name=director["full_name"],
            sic_description=sic_description,
            postcode=postcode,
            incorporation_date=profile.get("incorporation_date"),
            website_data=site,
            ch_events=ch_events,
            news_items=news_items,
        )
        counters["haiku_calls"] += 1
        out["raw_llm_response"] = raw[:2000] if raw else ""
    except Exception as e:
        print(f"  [warn] Haiku extraction failed: {e}", file=sys.stderr)
        parsed = None

    if not parsed or not parsed.get("hook"):
        out["confidence_research"] = "NONE"
        out["sources_used"] = ",".join(sources)
        out["research_notes"] = (parsed or {}).get("research_notes", "No hook found.")
        out["email_body"] = "SKIP_NO_HOOK"
        counters["none"] += 1
        return out

    out["hook"] = parsed.get("hook", "") or ""
    confidence = (parsed.get("confidence") or "").lower()
    out["confidence_research"] = {
        "high": "HIGH", "medium": "MEDIUM", "low": "LOW"
    }.get(confidence, "LOW")
    out["sources_used"] = ",".join(sources)
    out["research_notes"] = parsed.get("research_notes", "") or ""

    if out["confidence_research"] == "HIGH":
        counters["high"] += 1
    elif out["confidence_research"] == "MEDIUM":
        counters["medium"] += 1
    else:
        counters["low"] += 1

    # Email
    try:
        email = email_writer.generate_email(
            first_name=director["first_name"],
            hook_result=parsed,
            company_name=company_name,
            sic_description=sic_description,
            postcode=postcode,
        )
        out["subject"] = email["subject"]
        out["email_body"] = email["body"]
        out["opener"] = email["opener"]
    except Exception as e:
        print(f"  [warn] email generation failed: {e}", file=sys.stderr)
        out["email_body"] = "SKIP_NO_HOOK"

    return out


def main():
    ap = argparse.ArgumentParser(description="Tailored cold email outreach")
    ap.add_argument("--input", required=True, help="Input CSV (from domain-finder)")
    ap.add_argument("--output", default=None, help="Output CSV path")
    ap.add_argument("--dry-run", action="store_true",
                    help="Process first 5 rows, print output, don't write DB")
    ap.add_argument("--limit", type=int, default=None, help="Limit to first N rows")
    args = ap.parse_args()

    input_csv = args.input
    output_csv = args.output or os.getenv("OUTPUT_CSV", "./output.csv")
    db_path = os.getenv("DB_PATH", "./research.db")

    if not os.path.exists(input_csv):
        print(f"ERROR: input CSV not found: {input_csv}", file=sys.stderr)
        sys.exit(1)

    df = pd.read_csv(input_csv, dtype=str, keep_default_na=False)
    if args.dry_run:
        df = df.head(5)
    elif args.limit:
        df = df.head(args.limit)

    print(f"Loaded {len(df)} rows from {input_csv}")

    counters = {
        "ch_calls": 0, "serper_calls": 0, "haiku_calls": 0,
        "high": 0, "medium": 0, "low": 0, "none": 0, "processed": 0,
    }

    conn = None
    skip = set()
    if not args.dry_run:
        conn = open_db(db_path)
        skip = already_processed(conn)
        print(f"Already processed in DB: {len(skip)} — will skip those.")

    results = []
    for _, row_in in tqdm(df.iterrows(), total=len(df), desc="Processing"):
        cn = str(row_in.get("company_number", "")).strip()
        if not args.dry_run and cn in skip:
            continue
        try:
            out = process_one(row_in.to_dict(), counters)
        except Exception as e:
            traceback.print_exc()
            print(f"  [error] crashed on {cn}: {e}", file=sys.stderr)
            continue
        counters["processed"] += 1
        if conn:
            save_row(conn, out)
        results.append(out)
        if args.dry_run:
            print("\n" + "=" * 70)
            for k in OUTPUT_COLUMNS:
                v = out.get(k, "")
                if k == "email_body" and v and v != "SKIP_NO_HOOK":
                    print(f"{k}:\n{v}\n")
                else:
                    print(f"{k}: {v}")

    if conn and not args.dry_run:
        # Export full DB table to CSV so resumed runs still produce complete output
        full = pd.read_sql_query("SELECT * FROM research", conn)
        # Merge with input to keep original columns
        input_df = pd.read_csv(input_csv, dtype=str, keep_default_na=False)
        merged = input_df.merge(
            full[[c for c in full.columns if c not in input_df.columns or c == "company_number"]],
            on="company_number", how="left",
        )
        for col in OUTPUT_COLUMNS:
            if col not in merged.columns:
                merged[col] = ""
        merged[OUTPUT_COLUMNS].to_csv(output_csv, index=False)
        print(f"\nWrote {len(merged)} rows to {output_csv}")

    # Cost summary
    haiku_cost = counters["haiku_calls"] * 0.0008
    serper_cost = counters["serper_calls"] * 0.00024
    print("\n=== Summary ===")
    print(f"Processed:        {counters['processed']}")
    print(f"CH API calls:     {counters['ch_calls']}")
    print(f"Serper queries:   {counters['serper_calls']}  (~£{serper_cost:.4f})")
    print(f"Haiku calls:      {counters['haiku_calls']}   (~£{haiku_cost:.4f})")
    print(f"Estimated cost:   £{haiku_cost + serper_cost:.4f}")
    print(f"HIGH hooks:       {counters['high']}")
    print(f"MEDIUM hooks:     {counters['medium']}")
    print(f"LOW hooks:        {counters['low']}")
    print(f"NONE (skip):      {counters['none']}")


if __name__ == "__main__":
    main()
