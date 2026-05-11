from datetime import date, timedelta
from supabase import create_client
import os


def get_client():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])


def insert_post(db, platform: str, account_label: str, content: str, url: str, engagement_score: int) -> int:
    row = db.table("posts").insert({
        "platform": platform,
        "account_label": account_label,
        "content": content,
        "url": url,
        "engagement_score": engagement_score,
    }).execute()
    return row.data[0]["id"]


def insert_transcription(db, post_id: int, transcript: str):
    db.table("transcriptions").insert({
        "post_id": post_id,
        "transcript": transcript,
    }).execute()


def insert_summary(db, post_id: int, summary_pl: str, trend_tags: list, hook_type: str):
    db.table("summaries").insert({
        "post_id": post_id,
        "summary_pl": summary_pl,
        "trend_tags": trend_tags,
        "hook_type": hook_type,
    }).execute()


def insert_article(db, source_label: str, title: str, content: str, url: str, summary_pl: str, published_at):
    db.table("articles").insert({
        "source_label": source_label,
        "title": title,
        "content": content,
        "url": url,
        "summary_pl": summary_pl,
        "published_at": published_at,
    }).execute()


def insert_hook(db, post_id: int, hook_text: str, hook_type: str, why_it_works: str):
    db.table("hooks").insert({
        "post_id": post_id,
        "hook_text": hook_text,
        "hook_type": hook_type,
        "why_it_works": why_it_works,
    }).execute()


def upsert_trend_cluster(db, topic: str, status: str, cross_source_count: int,
                         total_engagement: int, engagement_delta: int, post_ids: list):
    existing = (
        db.table("trend_clusters")
        .select("id")
        .eq("topic", topic)
        .eq("last_seen", date.today().isoformat())
        .execute()
    )
    if existing.data:
        db.table("trend_clusters").update({
            "status": status,
            "cross_source_count": cross_source_count,
            "total_engagement": total_engagement,
            "engagement_delta": engagement_delta,
            "post_ids": post_ids,
        }).eq("id", existing.data[0]["id"]).execute()
    else:
        db.table("trend_clusters").insert({
            "topic": topic,
            "status": status,
            "cross_source_count": cross_source_count,
            "total_engagement": total_engagement,
            "engagement_delta": engagement_delta,
            "first_seen": date.today().isoformat(),
            "last_seen": date.today().isoformat(),
            "post_ids": post_ids,
        }).execute()


def get_posts_today(db) -> list:
    since = date.today().isoformat()
    return db.table("posts").select("*").gte("scraped_at", since).execute().data


def get_trend_history(db, days: int = 7) -> list:
    since = (date.today() - timedelta(days=days)).isoformat()
    return (
        db.table("trend_clusters")
        .select("topic, status, total_engagement, first_seen")
        .gte("last_seen", since)
        .execute()
        .data
    )


def get_today_clusters(db) -> list:
    return (
        db.table("trend_clusters")
        .select("*")
        .eq("last_seen", date.today().isoformat())
        .order("total_engagement", desc=True)
        .execute()
        .data
    )


def get_articles_today(db) -> list:
    since = date.today().isoformat()
    return db.table("articles").select("*").gte("published_at", since).execute().data


def get_top_posts_today(db, limit: int = 3) -> list:
    since = date.today().isoformat()
    return (
        db.table("posts")
        .select("*, summaries(*), hooks(*)")
        .gte("scraped_at", since)
        .order("engagement_score", desc=True)
        .limit(limit)
        .execute()
        .data
    )


def get_hooks_today(db) -> list:
    since = date.today().isoformat()
    return (
        db.table("hooks")
        .select("*, posts(engagement_score, account_label, url)")
        .gte("posts.scraped_at", since)
        .order("posts.engagement_score", desc=True)
        .limit(10)
        .execute()
        .data
    )


def save_report(db, pdf_path: str, audio_path: str) -> int:
    row = db.table("reports").insert({
        "pdf_path": pdf_path,
        "audio_path": audio_path,
    }).execute()
    return row.data[0]["id"]


def mark_report_sent(db, report_id: int):
    from datetime import datetime, timezone
    db.table("reports").update({
        "sent_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", report_id).execute()
