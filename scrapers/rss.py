"""Scrapes RSS feeds for AI newsletters and company blogs."""
import os
import yaml
from datetime import datetime, timezone, timedelta
import feedparser
from db.queries import get_client, insert_article


def load_accounts() -> dict:
    with open("accounts.yaml") as f:
        return yaml.safe_load(f)


def fetch_feed(url: str, label: str, since_hours: int = 26) -> list:
    feed = feedparser.parse(url)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    articles = []
    for entry in feed.entries:
        published = None
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        if published and published < cutoff:
            continue
        content = ""
        if hasattr(entry, "summary"):
            content = entry.summary
        elif hasattr(entry, "content"):
            content = entry.content[0].value if entry.content else ""
        articles.append({
            "source_label": label,
            "title": entry.get("title", ""),
            "content": content,
            "url": entry.get("link", ""),
            "published_at": published.isoformat() if published else datetime.now(timezone.utc).isoformat(),
        })
    return articles


def run():
    accounts = load_accounts()
    db = get_client()
    rss_sources = accounts.get("rss", [])

    all_articles = []
    for source in rss_sources:
        try:
            articles = fetch_feed(source["url"], source["label"])
            all_articles += articles
            print(f"[rss] {source['label']}: {len(articles)} articles")
        except Exception as e:
            print(f"[rss] ERROR {source['label']}: {e}")

    for article in all_articles:
        insert_article(
            db,
            source_label=article["source_label"],
            title=article["title"],
            content=article["content"],
            url=article["url"],
            summary_pl=None,
            published_at=article["published_at"],
        )

    print(f"[rss] total: {len(all_articles)} articles saved")
    return all_articles


if __name__ == "__main__":
    run()
