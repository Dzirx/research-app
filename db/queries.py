import json
import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.environ.get("DATABASE_PATH", os.path.join(os.path.dirname(__file__), "research.sqlite3"))
_SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    with open(_SCHEMA_PATH) as f:
        conn.executescript(f.read())
    return conn


@contextmanager
def get_conn():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_client() -> sqlite3.Connection:
    """Zwraca połączenie — alias dla kompatybilności z resztą kodu."""
    return _connect()


def _rows_to_dicts(rows) -> list:
    return [dict(r) for r in rows]


def insert_post(db, platform: str, account_label: str, content: str, url: str, engagement_score: int) -> int:
    cur = db.execute(
        """INSERT INTO posts (platform, account_label, content, url, engagement_score)
           VALUES (?, ?, ?, ?, ?)""",
        (platform, account_label, content, url, engagement_score),
    )
    db.commit()
    return cur.lastrowid


def insert_transcription(db, post_id: int, transcript: str):
    db.execute(
        "INSERT INTO transcriptions (post_id, transcript) VALUES (?, ?)",
        (post_id, transcript),
    )
    db.commit()


def insert_summary(db, post_id: int, summary_pl: str, trend_tags: list, hook_type: str):
    db.execute(
        "INSERT INTO summaries (post_id, summary_pl, trend_tags, hook_type) VALUES (?, ?, ?, ?)",
        (post_id, summary_pl, json.dumps(trend_tags, ensure_ascii=False), hook_type),
    )
    db.commit()


def insert_hook(db, post_id: int, hook_text: str, hook_type: str, why_it_works: str):
    db.execute(
        "INSERT INTO hooks (post_id, hook_text, hook_type, why_it_works) VALUES (?, ?, ?, ?)",
        (post_id, hook_text, hook_type, why_it_works),
    )
    db.commit()


def upsert_trend_cluster(db, topic: str, status: str, cross_source_count: int,
                         total_engagement: int, engagement_delta: int, post_ids: list):
    row = db.execute(
        "SELECT id FROM trend_clusters WHERE topic = ? AND last_seen = date('now')",
        (topic,),
    ).fetchone()
    post_ids_json = json.dumps(post_ids)
    if row:
        db.execute(
            """UPDATE trend_clusters
               SET status=?, cross_source_count=?, total_engagement=?,
                   engagement_delta=?, post_ids=?
               WHERE id=?""",
            (status, cross_source_count, total_engagement, engagement_delta, post_ids_json, row["id"]),
        )
    else:
        db.execute(
            """INSERT INTO trend_clusters
               (topic, status, cross_source_count, total_engagement, engagement_delta,
                first_seen, last_seen, post_ids)
               VALUES (?, ?, ?, ?, ?, date('now'), date('now'), ?)""",
            (topic, status, cross_source_count, total_engagement, engagement_delta, post_ids_json),
        )
    db.commit()


def get_posts_today(db) -> list:
    rows = db.execute("SELECT * FROM posts WHERE date(scraped_at) = date('now')").fetchall()
    return _rows_to_dicts(rows)


def get_trend_history(db, days: int = 7) -> list:
    rows = db.execute(
        "SELECT topic, status, total_engagement, first_seen FROM trend_clusters WHERE last_seen >= date('now', ?)",
        (f"-{days} days",),
    ).fetchall()
    return _rows_to_dicts(rows)


def get_today_clusters(db) -> list:
    rows = db.execute(
        "SELECT * FROM trend_clusters WHERE last_seen = date('now') ORDER BY total_engagement DESC"
    ).fetchall()
    clusters = _rows_to_dicts(rows)
    for c in clusters:
        c["post_ids"] = json.loads(c["post_ids"] or "[]")
    return clusters


def get_top_posts_today(db, limit: int = 3) -> list:
    rows = db.execute(
        """SELECT p.*, s.summary_pl, h.hook_text, h.why_it_works
           FROM posts p
           LEFT JOIN summaries s ON s.post_id = p.id
           LEFT JOIN hooks h ON h.post_id = p.id
           WHERE date(p.scraped_at) = date('now')
           ORDER BY p.engagement_score DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()
    return _rows_to_dicts(rows)


def get_hooks_today(db) -> list:
    rows = db.execute(
        """SELECT h.*, p.engagement_score, p.account_label, p.url
           FROM hooks h
           JOIN posts p ON p.id = h.post_id
           WHERE date(p.scraped_at) = date('now')
           ORDER BY p.engagement_score DESC
           LIMIT 10"""
    ).fetchall()
    return _rows_to_dicts(rows)


def get_post_summary(db, post_id: int) -> str | None:
    row = db.execute(
        "SELECT summary_pl FROM summaries WHERE post_id = ? LIMIT 1", (post_id,)
    ).fetchone()
    return row["summary_pl"] if row else None


def insert_own_post(db, content: str, url: str):
    db.execute(
        "INSERT OR IGNORE INTO own_posts (content, url) VALUES (?, ?)",
        (content, url),
    )
    db.commit()


def get_own_posts_recent(db, days: int = 14) -> list:
    rows = db.execute(
        "SELECT * FROM own_posts WHERE scraped_at >= datetime('now', ?)",
        (f"-{days} days",),
    ).fetchall()
    return _rows_to_dicts(rows)


def insert_script_idea(db, topic: str, hook: str, body: str, cta: str) -> int:
    cur = db.execute(
        "INSERT INTO script_ideas (topic, hook, body, cta) VALUES (?, ?, ?, ?)",
        (topic, hook, body, cta),
    )
    db.commit()
    return cur.lastrowid


def get_recent_script_ideas(db, days: int = 60) -> list:
    rows = db.execute(
        "SELECT * FROM script_ideas WHERE created_at >= datetime('now', ?) ORDER BY created_at DESC",
        (f"-{days} days",),
    ).fetchall()
    return _rows_to_dicts(rows)


def get_pending_script_ideas(db, days: int = 60) -> list:
    rows = db.execute(
        "SELECT * FROM script_ideas WHERE status = 'proposed' AND created_at >= datetime('now', ?)",
        (f"-{days} days",),
    ).fetchall()
    return _rows_to_dicts(rows)


def mark_script_idea_published(db, idea_id: int, matched_post_url: str):
    db.execute(
        "UPDATE script_ideas SET status = 'published', matched_post_url = ? WHERE id = ?",
        (matched_post_url, idea_id),
    )
    db.commit()


def save_report(db, pdf_path: str, audio_path: str) -> int:
    cur = db.execute(
        "INSERT INTO reports (pdf_path, audio_path) VALUES (?, ?)",
        (pdf_path, audio_path),
    )
    db.commit()
    return cur.lastrowid


def mark_report_sent(db, report_id: int):
    db.execute("UPDATE reports SET sent_at = datetime('now') WHERE id = ?", (report_id,))
    db.commit()
