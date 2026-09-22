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


def _load_json_field(row: dict, field: str) -> list:
    try:
        return json.loads(row.get(field) or "[]")
    except (TypeError, json.JSONDecodeError):
        return []


def insert_post(db, platform: str, account_label: str, content: str, url: str,
                engagement_score: int) -> tuple[int, bool]:
    """
    Zapisuje post, deduplikując po URL — okno scrapingu jest szersze niż doba,
    więc ten sam post wraca z Apify kilka dni z rzędu.

    Zwraca (post_id, is_new). Dla znanego URL-a aktualizujemy tylko engagement_score
    (zbiera lajki po publikacji) i zostawiamy scraped_at, żeby data pierwszego
    zobaczenia się nie przesuwała — to na niej stoi "co nowego dziś" w raporcie.
    """
    existing = db.execute("SELECT id FROM posts WHERE url = ? AND url != ''", (url,)).fetchone()
    if existing:
        db.execute(
            "UPDATE posts SET engagement_score = ? WHERE id = ?",
            (engagement_score, existing["id"]),
        )
        db.commit()
        return existing["id"], False

    cur = db.execute(
        """INSERT INTO posts (platform, account_label, content, url, engagement_score)
           VALUES (?, ?, ?, ?, ?)""",
        (platform, account_label, content, url, engagement_score),
    )
    db.commit()
    return cur.lastrowid, True


def insert_transcription(db, post_id: int, transcript: str):
    db.execute(
        """INSERT INTO transcriptions (post_id, transcript) VALUES (?, ?)
           ON CONFLICT(post_id) DO UPDATE SET transcript = excluded.transcript""",
        (post_id, transcript),
    )
    db.commit()


def insert_summary(db, post_id: int, summary_pl: str, trend_tags: list, hook_type: str,
                   key_points: list | None = None):
    db.execute(
        """INSERT INTO summaries (post_id, summary_pl, trend_tags, hook_type, key_points)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(post_id) DO UPDATE SET
               summary_pl = excluded.summary_pl,
               trend_tags = excluded.trend_tags,
               hook_type  = excluded.hook_type,
               key_points = excluded.key_points""",
        (
            post_id,
            summary_pl,
            json.dumps(trend_tags, ensure_ascii=False),
            hook_type,
            json.dumps(key_points or [], ensure_ascii=False),
        ),
    )
    db.commit()


def insert_hook(db, post_id: int, hook_text: str, hook_type: str, why_it_works: str):
    """
    Jeden hook na post. Model potrafi zwrócić tę samą analizę dwa razy (widziane na
    produkcji: ten sam post dostał dwa identyczne hooki i pokazał się dwukrotnie
    w sekcji V). Deduplikujemy w kodzie, a nie indeksem UNIQUE, żeby działało też
    na bazach, w których duplikaty już siedzą.
    """
    existing = db.execute("SELECT id FROM hooks WHERE post_id = ?", (post_id,)).fetchone()
    if existing:
        db.execute(
            "UPDATE hooks SET hook_text = ?, hook_type = ?, why_it_works = ? WHERE id = ?",
            (hook_text, hook_type, why_it_works, existing["id"]),
        )
    else:
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
    """Posty zobaczone po raz pierwszy dzisiaj, razem z transkrypcją (jeśli jest)."""
    rows = db.execute(
        """SELECT p.*, t.transcript
           FROM posts p
           LEFT JOIN transcriptions t ON t.post_id = p.id
           WHERE date(p.scraped_at) = date('now')"""
    ).fetchall()
    return _rows_to_dicts(rows)


def get_cluster_source_material(db, post_ids: list) -> list:
    """
    Pełny materiał źródłowy klastra — to, na czym mają stać skrypty wideo i fact-check.
    Bez tego generator dostawałby samą nazwę tematu i musiałby zmyślać treść.
    """
    ids = [int(pid) for pid in post_ids if pid]
    if not ids:
        return []
    placeholders = ",".join("?" for _ in ids)
    rows = db.execute(
        f"""SELECT p.id, p.account_label, p.url, p.engagement_score, p.content,
                   s.summary_pl, s.key_points, h.hook_text, t.transcript
            FROM posts p
            LEFT JOIN summaries s ON s.post_id = p.id
            LEFT JOIN hooks h ON h.post_id = p.id
            LEFT JOIN transcriptions t ON t.post_id = p.id
            WHERE p.id IN ({placeholders})
            GROUP BY p.id
            ORDER BY p.engagement_score DESC""",
        ids,
    ).fetchall()
    material = _rows_to_dicts(rows)
    for item in material:
        item["key_points"] = _load_json_field(item, "key_points")
    return material


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
        c["post_ids"] = _load_json_field(c, "post_ids")
    return clusters


def get_top_posts_today(db, limit: int = 3) -> list:
    rows = db.execute(
        """SELECT p.*, s.summary_pl, s.key_points, h.hook_text, h.why_it_works
           FROM posts p
           LEFT JOIN summaries s ON s.post_id = p.id
           LEFT JOIN hooks h ON h.post_id = p.id
           WHERE date(p.scraped_at) = date('now')
           GROUP BY p.id
           ORDER BY p.engagement_score DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()
    posts = _rows_to_dicts(rows)
    for post in posts:
        post["key_points"] = _load_json_field(post, "key_points")
    return posts


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


def insert_script_idea(db, topic: str, hook: str, body: str, cta: str,
                       source_url: str = "", source_note: str = "") -> int:
    cur = db.execute(
        """INSERT INTO script_ideas (topic, hook, body, cta, source_url, source_note)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (topic, hook, body, cta, source_url, source_note),
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
