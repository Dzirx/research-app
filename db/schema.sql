CREATE TABLE IF NOT EXISTS posts (
    id BIGSERIAL PRIMARY KEY,
    platform TEXT NOT NULL,
    account_label TEXT NOT NULL,
    content TEXT,
    url TEXT,
    scraped_at TIMESTAMPTZ DEFAULT NOW(),
    engagement_score INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS transcriptions (
    id BIGSERIAL PRIMARY KEY,
    post_id BIGINT REFERENCES posts(id) ON DELETE CASCADE,
    transcript TEXT,
    model_used TEXT DEFAULT 'whisper-1'
);

CREATE TABLE IF NOT EXISTS summaries (
    id BIGSERIAL PRIMARY KEY,
    post_id BIGINT REFERENCES posts(id) ON DELETE CASCADE,
    summary_pl TEXT,
    trend_tags TEXT[],
    hook_type TEXT
);

CREATE TABLE IF NOT EXISTS trend_clusters (
    id BIGSERIAL PRIMARY KEY,
    topic TEXT NOT NULL,
    status TEXT NOT NULL,          -- breaking / trending / recurring / fading
    cross_source_count INTEGER DEFAULT 1,
    total_engagement INTEGER DEFAULT 0,
    engagement_delta INTEGER DEFAULT 0,
    first_seen DATE,
    last_seen DATE DEFAULT CURRENT_DATE,
    post_ids BIGINT[]
);

CREATE TABLE IF NOT EXISTS articles (
    id BIGSERIAL PRIMARY KEY,
    source_label TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT,
    url TEXT,
    summary_pl TEXT,
    published_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS hooks (
    id BIGSERIAL PRIMARY KEY,
    post_id BIGINT REFERENCES posts(id) ON DELETE CASCADE,
    hook_text TEXT NOT NULL,
    hook_type TEXT,
    why_it_works TEXT
);

CREATE TABLE IF NOT EXISTS reports (
    id BIGSERIAL PRIMARY KEY,
    generated_at TIMESTAMPTZ DEFAULT NOW(),
    pdf_path TEXT,
    audio_path TEXT,
    sent_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_posts_scraped_at ON posts(scraped_at DESC);
CREATE INDEX IF NOT EXISTS idx_posts_platform ON posts(platform);
CREATE INDEX IF NOT EXISTS idx_articles_published_at ON articles(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_trend_clusters_last_seen ON trend_clusters(last_seen DESC);
