"""Scrapes Instagram (Reels + Posts) and Facebook via Apify."""
import os
import yaml
from apify_client import ApifyClient
from db.queries import get_client, insert_post


def load_accounts() -> dict:
    with open("accounts.yaml") as f:
        return yaml.safe_load(f)


def scrape_instagram_reels(client: ApifyClient, accounts: list) -> list:
    results = []
    label_map = {a["url"].rstrip("/").split("/")[-1]: a["label"] for a in accounts}
    run = client.actor("apify/instagram-reel-scraper").call(run_input={
        "directUrls": [a["url"] for a in accounts],
        "resultsLimit": 10,
        "onlyPostsNewerThan": "26 hours",
    })
    for item in client.dataset(run["defaultDatasetId"]).iterate_items():
        username = item.get("ownerUsername", "")
        transcript = item.get("transcript", "") or ""
        caption = item.get("caption", "") or ""
        content = caption
        if transcript:
            content = f"{caption}\n\n[TRANSKRYPCJA]: {transcript}".strip()
        results.append({
            "platform": "instagram",
            "account_label": label_map.get(username, username),
            "content": content,
            "url": item.get("url", ""),
            "engagement_score": (
                (item.get("likesCount") or 0)
                + (item.get("commentsCount") or 0) * 3
                + (item.get("sharesCount") or 0) * 5
                + (item.get("videoPlayCount") or 0) // 10
            ),
            "video_url": item.get("videoUrl"),
        })
    return results


def scrape_instagram_posts(client: ApifyClient, accounts: list) -> list:
    results = []
    label_map = {a["url"].rstrip("/").split("/")[-1]: a["label"] for a in accounts}
    run = client.actor("apify/instagram-post-scraper").call(run_input={
        "directUrls": [a["url"] for a in accounts],
        "resultsLimit": 10,
    })
    for item in client.dataset(run["defaultDatasetId"]).iterate_items():
        username = item.get("ownerUsername", "")
        results.append({
            "platform": "instagram",
            "account_label": label_map.get(username, username),
            "content": item.get("caption", "") or "",
            "url": item.get("url", ""),
            "engagement_score": (
                (item.get("likesCount") or 0)
                + (item.get("commentsCount") or 0) * 3
            ),
            "video_url": None,
        })
    return results


def scrape_facebook(client: ApifyClient, accounts: list) -> list:
    results = []
    label_map = {a["url"]: a["label"] for a in accounts}
    run = client.actor("apify/facebook-posts-scraper").call(run_input={
        "startUrls": [{"url": a["url"]} for a in accounts],
        "resultsLimit": 10,
        "onlyPostsNewerThan": "26 hours",
    })
    for item in client.dataset(run["defaultDatasetId"]).iterate_items():
        input_url = item.get("inputUrl", "")
        label = next((v for k, v in label_map.items() if k in input_url), item.get("pageName", input_url))
        results.append({
            "platform": "facebook",
            "account_label": label,
            "content": item.get("text", ""),
            "url": item.get("url", ""),
            "engagement_score": (
                (item.get("likes") or 0)
                + (item.get("comments") or 0) * 3
                + (item.get("shares") or 0) * 5
                + (item.get("viewsCount") or 0) // 10
            ),
            "video_url": None,
        })
    return results


def run():
    accounts = load_accounts()
    apify = ApifyClient(os.environ["APIFY_TOKEN"])
    db = get_client()

    all_posts = []
    if accounts.get("instagram"):
        # Reelsy mają wbudowany transcript — scrapeujemy osobno
        reels = scrape_instagram_reels(apify, accounts["instagram"])
        posts = scrape_instagram_posts(apify, accounts["instagram"])
        # deduplikacja po url — reel wygrywa nad postem jeśli ten sam url
        seen_urls = {r["url"] for r in reels}
        posts = [p for p in posts if p["url"] not in seen_urls]
        all_posts += reels + posts

    if accounts.get("facebook"):
        all_posts += scrape_facebook(apify, accounts["facebook"])

    for post in all_posts:
        post_id = insert_post(
            db,
            platform=post["platform"],
            account_label=post["account_label"],
            content=post["content"],
            url=post["url"],
            engagement_score=post["engagement_score"],
        )
        post["db_id"] = post_id

    print(f"[social] scraped {len(all_posts)} posts")
    return all_posts


if __name__ == "__main__":
    run()
