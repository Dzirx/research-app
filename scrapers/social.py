"""Scrapes Instagram and Facebook posts via Apify."""
import os
import yaml
from apify_client import ApifyClient
from db.queries import get_client, insert_post


def load_accounts() -> dict:
    with open("accounts.yaml") as f:
        return yaml.safe_load(f)


def scrape_instagram(client: ApifyClient, accounts: list) -> list:
    results = []
    usernames = [a["url"].rstrip("/").split("/")[-1] for a in accounts]
    run = client.actor("apify/instagram-scraper").call(run_input={
        "directUrls": [a["url"] for a in accounts],
        "resultsType": "posts",
        "resultsLimit": 10,
        "addParentData": False,
    })
    items = client.dataset(run["defaultDatasetId"]).iterate_items()
    label_map = {a["url"].rstrip("/").split("/")[-1]: a["label"] for a in accounts}
    for item in items:
        username = item.get("ownerUsername", "")
        results.append({
            "platform": "instagram",
            "account_label": label_map.get(username, username),
            "content": item.get("caption", "") or item.get("alt", ""),
            "url": item.get("url", ""),
            "engagement_score": (
                (item.get("likesCount") or 0)
                + (item.get("commentsCount") or 0) * 3
                + (item.get("videoPlayCount") or 0) // 10
            ),
            "video_url": item.get("videoUrl"),
        })
    return results


def scrape_facebook(client: ApifyClient, accounts: list) -> list:
    results = []
    run = client.actor("apify/facebook-pages-scraper").call(run_input={
        "startUrls": [{"url": a["url"]} for a in accounts],
        "maxPosts": 10,
    })
    items = client.dataset(run["defaultDatasetId"]).iterate_items()
    label_map = {a["url"]: a["label"] for a in accounts}
    for item in items:
        page_url = item.get("pageUrl", "")
        label = next((v for k, v in label_map.items() if k in page_url), page_url)
        for post in item.get("posts", []):
            results.append({
                "platform": "facebook",
                "account_label": label,
                "content": post.get("text", ""),
                "url": post.get("url", ""),
                "engagement_score": (
                    (post.get("likes") or 0)
                    + (post.get("comments") or 0) * 3
                    + (post.get("shares") or 0) * 5
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
        all_posts += scrape_instagram(apify, accounts["instagram"])
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
