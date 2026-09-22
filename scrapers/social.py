"""Scrapes Instagram (Reels + Posts) and Facebook via Apify."""
import os
import yaml
from apify_client import ApifyClient
from db.queries import get_client, insert_post, insert_own_post

# Okno szersze niż doba, bo śledzone konta nie publikują codziennie — przy "1 day"
# raport regularnie wychodził pusty. Duplikaty odsiewa UNIQUE na posts.url.
DEFAULT_SCRAPE_WINDOW = "3 days"

# Instagram trzyma rolki w osobnej zakładce i część z nich nie trafia do siatki profilu.
# Sam post-scraper gubił przez to jedną trzecią materiału (zmierzone: 8 z 12 rolek
# z 3 dni), w tym najciekawsze — bo to właśnie rolki mają transkrypcje. Odpytujemy
# oba źródła i scalamy; nakładające się wyniki odsiewa dedup po URL.
INSTAGRAM_ACTORS = [
    ("apify/instagram-post-scraper", "siatka profilu"),
    ("apify/instagram-reel-scraper", "zakładka Reels"),
]


def load_accounts() -> dict:
    with open("accounts.yaml") as f:
        return yaml.safe_load(f)


def get_scrape_window(accounts: dict) -> str:
    return (accounts.get("scrape_window") or DEFAULT_SCRAPE_WINDOW).strip()


def scrape_instagram_posts(client: ApifyClient, accounts: list, window: str,
                           actor: str = "apify/instagram-post-scraper") -> list:
    """Oba aktory zwracają te same pola, więc mapowanie jest wspólne."""
    results = []
    label_map = {a["url"].rstrip("/").split("/")[-1].lower(): a["label"] for a in accounts}
    usernames = [a["url"].rstrip("/").split("/")[-1] for a in accounts]
    run = client.actor(actor).call(run_input={
        "username": usernames,
        "resultsLimit": 10,
        "onlyPostsNewerThan": window,
        "skipPinnedPosts": True,
    })
    for item in client.dataset(run["defaultDatasetId"]).iterate_items():
        username = (item.get("ownerUsername") or "").lower()
        content = item.get("caption", "") or ""
        if not username and not content:
            # Apify czasem zwraca puste/błędne wpisy (np. po nieudanym pobraniu konta) —
            # bez ownera i bez treści nie da się ich sensownie przeanalizować ani przypisać.
            print(f"[social] pomijam pusty wpis: {item.get('url') or item.get('id')}")
            continue
        if item.get("isPinned"):
            # reel-scraper nie zna skipPinnedPosts, więc przypięte odsiewamy tutaj
            continue
        results.append({
            "platform": "instagram",
            "account_label": label_map.get(username, username or "nieznane"),
            "content": content,
            "url": item.get("url", ""),
            "video_url": item.get("videoUrl"),
            "engagement_score": (
                (item.get("likesCount") or 0)
                + (item.get("commentsCount") or 0) * 3
                + (item.get("videoPlayCount") or 0) // 10
            ),
        })
    return results


def scrape_facebook(client: ApifyClient, accounts: list, window: str) -> list:
    results = []
    label_map = {a["url"]: a["label"] for a in accounts}
    run = client.actor("apify/facebook-posts-scraper").call(run_input={
        "startUrls": [{"url": a["url"]} for a in accounts],
        "resultsLimit": 10,
        "onlyPostsNewerThan": window,
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
        })
    return results


def run():
    """
    Zwraca WYŁĄCZNIE posty widziane po raz pierwszy. Znane URL-e dostają tylko
    świeży engagement_score i nie idą dalej — nie ma po co drugi raz płacić
    za transkrypcję i analizę tego samego materiału.
    """
    accounts = load_accounts()
    window = get_scrape_window(accounts)
    apify = ApifyClient(os.environ["APIFY_TOKEN"])
    db = get_client()

    print(f"[social] okno scrapingu: {window}")

    all_posts = []
    if accounts.get("instagram"):
        for actor, opis in INSTAGRAM_ACTORS:
            found = scrape_instagram_posts(apify, accounts["instagram"], window, actor)
            print(f"[social] {opis}: {len(found)} pozycji")
            all_posts += found

    if accounts.get("facebook"):
        all_posts += scrape_facebook(apify, accounts["facebook"], window)

    new_posts = []
    known = 0
    for post in all_posts:
        post_id, is_new = insert_post(
            db,
            platform=post["platform"],
            account_label=post["account_label"],
            content=post["content"],
            url=post["url"],
            engagement_score=post["engagement_score"],
        )
        post["db_id"] = post_id
        post["id"] = post_id
        if is_new:
            new_posts.append(post)
        else:
            known += 1

    print(f"[social] {len(new_posts)} nowych, {known} już znanych (zaktualizowano engagement)")

    own_accounts = accounts.get("own_account") or []
    if own_accounts:
        own_posts = []
        for actor, _ in INSTAGRAM_ACTORS:
            own_posts += scrape_instagram_posts(apify, own_accounts, window, actor)
        for post in own_posts:
            insert_own_post(db, content=post["content"], url=post["url"])
        print(f"[social] scraped {len(own_posts)} own posts (do wykrywania publikacji)")

    return new_posts


if __name__ == "__main__":
    run()
