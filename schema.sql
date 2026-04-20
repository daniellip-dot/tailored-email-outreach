CREATE TABLE IF NOT EXISTS research (
    company_number         TEXT PRIMARY KEY,
    company_name           TEXT,
    domain                 TEXT,
    director_first_name    TEXT,
    director_last_name     TEXT,
    director_full_name     TEXT,
    hook                   TEXT,
    opener                 TEXT,
    subject                TEXT,
    email_body             TEXT,
    confidence_research    TEXT,
    sources_used           TEXT,
    research_notes         TEXT,
    website_text_sample    TEXT,
    raw_llm_response       TEXT,
    processed_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
