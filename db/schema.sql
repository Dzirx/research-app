CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    account_label TEXT NOT NULL,
    content TEXT,
    url TEXT,
    scraped_at TEXT NOT NULL DEFAULT (datetime('now')),
    engagement_score INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS transcriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER REFERENCES posts(id) ON DELETE CASCADE,
    transcript TEXT,
    model_used TEXT DEFAULT 'whisper-1'
);

CREATE TABLE IF NOT EXISTS summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER REFERENCES posts(id) ON DELETE CASCADE,
    summary_pl TEXT,
    trend_tags TEXT,        -- JSON array, np. ["prompt engineering", "GPT-5"]
    hook_type TEXT
);

CREATE TABLE IF NOT EXISTS trend_clusters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT NOT NULL,
    status TEXT NOT NULL,          -- breaking / trending / recurring / fading
    cross_source_count INTEGER DEFAULT 1,
    total_engagement INTEGER DEFAULT 0,
    engagement_delta INTEGER DEFAULT 0,
    first_seen TEXT,
    last_seen TEXT DEFAULT (date('now')),
    post_ids TEXT            -- JSON array of post ids
);

CREATE TABLE IF NOT EXISTS hooks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER REFERENCES posts(id) ON DELETE CASCADE,
    hook_text TEXT NOT NULL,
    hook_type TEXT,
    why_it_works TEXT
);

CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    generated_at TEXT NOT NULL DEFAULT (datetime('now')),
    pdf_path TEXT,
    audio_path TEXT,
    sent_at TEXT
);

-- Twoje własne opublikowane posty (np. mati.olejarski) — używane wyłącznie do
-- wykrywania, które zaproponowane pomysły na rolkę zostały już zrealizowane.
CREATE TABLE IF NOT EXISTS own_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT,
    url TEXT UNIQUE,
    scraped_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Rejestr pomysłów na skrypty wideo zaproponowanych przez raport — zapobiega
-- powtarzaniu tych samych motywów, gdy widać po own_posts, że już je nagrałeś.
CREATE TABLE IF NOT EXISTS script_ideas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT NOT NULL,
    hook TEXT,
    body TEXT,
    cta TEXT,
    status TEXT NOT NULL DEFAULT 'proposed',   -- proposed / published
    matched_post_url TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_posts_scraped_at ON posts(scraped_at DESC);
CREATE INDEX IF NOT EXISTS idx_posts_platform ON posts(platform);
CREATE INDEX IF NOT EXISTS idx_trend_clusters_last_seen ON trend_clusters(last_seen DESC);
CREATE INDEX IF NOT EXISTS idx_script_ideas_created_at ON script_ideas(created_at DESC);
