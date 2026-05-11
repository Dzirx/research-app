import os
from contextlib import contextmanager
from datetime import date, timedelta
import psycopg2
import psycopg2.extras


@contextmanager
def get_conn():
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_client():
    """Zwraca połączenie — alias dla kompatybilności z resztą kodu."""
    return psycopg2.connect(os.environ["DATABASE_URL"])


def insert_post(db, platform: str, account_label: str, content: str, url: str, engagement_score: int) -> int:
    with db.cursor() as cur:
        cur.execute(
            """INSERT INTO posts (platform, account_label, content, url, engagement_score)
               VALUES (%s, %s, %s, %s, %s) RETURNING id""",
            (platform, account_label, content, url, engagement_score),
        )
        post_id = cur.fetchone()[0]
    db.commit()
    return post_id


def insert_transcription(db, post_id: int, transcript: str):
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO transcriptions (post_id, transcript) VALUES (%s, %s)",
            (post_id, transcript),
        )
    db.commit()


def insert_summary(db, post_id: int, summary_pl: str, trend_tags: list, hook_type: str):
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO summaries (post_id, summary_pl, trend_tags, hook_type) VALUES (%s, %s, %s, %s)",
            (post_id, summary_pl, trend_tags, hook_type),
        )
    db.commit()


def insert_article(db, source_label: str, title: str, content: str, url: str, summary_pl: str, published_at):
    with db.cursor() as cur:
        cur.execute(
            """INSERT INTO articles (source_label, title, content, url, summary_pl, published_at)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (source_label, title, content, url, summary_pl, published_at),
        )
    db.commit()


def insert_hook(db, post_id: int, hook_text: str, hook_type: str, why_it_works: str):
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO hooks (post_id, hook_text, hook_type, why_it_works) VALUES (%s, %s, %s, %s)",
            (post_id, hook_text, hook_type, why_it_works),
        )
    db.commit()


def upsert_trend_cluster(db, topic: str, status: str, cross_source_count: int,
                         total_engagement: int, engagement_delta: int, post_ids: list):
    with db.cursor() as cur:
        cur.execute(
            "SELECT id FROM trend_clusters WHERE topic = %s AND last_seen = CURRENT_DATE",
            (topic,),
        )
        row = cur.fetchone()
        if row:
            cur.execute(
                """UPDATE trend_clusters
                   SET status=%s, cross_source_count=%s, total_engagement=%s,
                       engagement_delta=%s, post_ids=%s
                   WHERE id=%s""",
                (status, cross_source_count, total_engagement, engagement_delta, post_ids, row[0]),
            )
        else:
            cur.execute(
                """INSERT INTO trend_clusters
                   (topic, status, cross_source_count, total_engagement, engagement_delta,
                    first_seen, last_seen, post_ids)
                   VALUES (%s, %s, %s, %s, %s, CURRENT_DATE, CURRENT_DATE, %s)""",
                (topic, status, cross_source_count, total_engagement, engagement_delta, post_ids),
            )
    db.commit()


def get_posts_today(db) -> list:
    with db.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM posts WHERE scraped_at >= CURRENT_DATE")
        return [dict(r) for r in cur.fetchall()]


def get_trend_history(db, days: int = 7) -> list:
    with db.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT topic, status, total_engagement, first_seen FROM trend_clusters WHERE last_seen >= CURRENT_DATE - %s",
            (days,),
        )
        return [dict(r) for r in cur.fetchall()]


def get_today_clusters(db) -> list:
    with db.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT * FROM trend_clusters WHERE last_seen = CURRENT_DATE ORDER BY total_engagement DESC"
        )
        return [dict(r) for r in cur.fetchall()]


def get_articles_today(db) -> list:
    with db.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM articles WHERE published_at >= CURRENT_DATE")
        return [dict(r) for r in cur.fetchall()]


def get_top_posts_today(db, limit: int = 3) -> list:
    with db.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """SELECT p.*, s.summary_pl, h.hook_text, h.why_it_works
               FROM posts p
               LEFT JOIN summaries s ON s.post_id = p.id
               LEFT JOIN hooks h ON h.post_id = p.id
               WHERE p.scraped_at >= CURRENT_DATE
               ORDER BY p.engagement_score DESC
               LIMIT %s""",
            (limit,),
        )
        return [dict(r) for r in cur.fetchall()]


def get_hooks_today(db) -> list:
    with db.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """SELECT h.*, p.engagement_score, p.account_label, p.url
               FROM hooks h
               JOIN posts p ON p.id = h.post_id
               WHERE p.scraped_at >= CURRENT_DATE
               ORDER BY p.engagement_score DESC
               LIMIT 10"""
        )
        return [dict(r) for r in cur.fetchall()]


def save_report(db, pdf_path: str, audio_path: str) -> int:
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO reports (pdf_path, audio_path) VALUES (%s, %s) RETURNING id",
            (pdf_path, audio_path),
        )
        report_id = cur.fetchone()[0]
    db.commit()
    return report_id


def mark_report_sent(db, report_id: int):
    with db.cursor() as cur:
        cur.execute(
            "UPDATE reports SET sent_at = NOW() WHERE id = %s",
            (report_id,),
        )
    db.commit()
