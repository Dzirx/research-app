"""
Analyzes posts + RSS articles with GPT-4o mini.
Produces: per-post summaries, hooks, and trend clusters (with historical context).

Two-stage approach:
  Stage 1 — summarize posts in batches of 5 (short output per post)
  Stage 2 — detect trends using only trend_tags (very small prompt)
             engagement_delta computed in Python, not by GPT
"""
import json
import os
from openai import OpenAI
from db.queries import (
    get_client, get_posts_today, get_trend_history,
    insert_summary, insert_hook, upsert_trend_cluster,
)

BATCH_SIZE = 5

SUMMARY_SYSTEM = """Jesteś analitykiem contentu AI. Odpowiadasz TYLKO poprawnym JSON-em.
Dla każdego posta zwróć obiekt z polami:
- index: numer z wejścia (bez zmian)
- summary_pl: 3-4 zdania po polsku opisujące sedno posta — co twórca przekazuje, jaką wiedzę lub opinię
- hook_type: jeden z: FOMO | controversy | demo | breaking_news | secret_trick | educational | social_proof
- hook_text: dosłowny lub sparafrazowany fragment który jest hookiem (pierwsze zdanie/tytuł który zatrzymuje)
- why_it_works: 1-2 zdania dlaczego ten hook działa psychologicznie
- trend_tags: lista 1-3 słów kluczowych (np. ["GPT-5", "prompt engineering"])
Format: {"posts": [...]}
"""

TREND_SYSTEM = """Jesteś analitykiem trendów AI. Odpowiadasz TYLKO poprawnym JSON-em.
Masz tagi tematyczne postów z dziś oraz listę tematów z historii ostatnich 7 dni.
Pogrupuj posty w klastry tematyczne i dla każdego klastra zwróć:
- topic: nazwa tematu (2-4 słowa)
- status: "breaking" | "trending" | "recurring" | "fading"
  breaking  = temat nie występuje w historii_7d
  trending  = temat jest w historii_7d i dziś ma więcej wzmianek/engagement
  recurring = temat jest w historii_7d, podobny poziom
  fading    = temat jest w historii_7d, dziś mniej wzmianek
- cross_source_count: ile różnych kont mówi o tym temacie dziś
- total_engagement: suma engagement postów w klastrze
- post_indices: lista indeksów postów które należą do klastra
NIE zwracaj engagement_delta — to obliczy kod.
Format: {"clusters": [...]}
"""


def build_history_avg(history: list) -> dict:
    """Buduje mapę topic → średni engagement z ostatnich 7 dni."""
    topic_totals: dict[str, list[int]] = {}
    for h in history:
        topic = h["topic"]
        eng = h.get("total_engagement") or 0
        topic_totals.setdefault(topic, []).append(eng)
    return {topic: int(sum(vals) / len(vals)) for topic, vals in topic_totals.items()}


def compute_delta(cluster_topic: str, total_engagement: int, history_avg: dict) -> int:
    """Liczy różnicę między dzisiejszym engagementem a średnią historyczną."""
    avg = history_avg.get(cluster_topic)
    if avg is None:
        # szukamy częściowego dopasowania tematów (np. "GPT-5" w "GPT-5 release")
        for topic, val in history_avg.items():
            if cluster_topic.lower() in topic.lower() or topic.lower() in cluster_topic.lower():
                return total_engagement - val
        return 0
    return total_engagement - avg


def analyze_batch(openai_client: OpenAI, batch: list, offset: int) -> list:
    payload = [
        {
            "index": offset + i,
            "platform": p.get("platform"),
            "account": p.get("account_label"),
            "content": p.get("content", "")[:2000],
            "engagement": p.get("engagement_score", 0),
        }
        for i, p in enumerate(batch)
    ]
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SUMMARY_SYSTEM},
            {"role": "user", "content": f"Przeanalizuj te posty:\n{json.dumps(payload, ensure_ascii=False)}"},
        ],
        response_format={"type": "json_object"},
    )
    data = json.loads(response.choices[0].message.content)
    return data.get("posts") or []


def analyze_posts_batched(openai_client: OpenAI, posts: list) -> list:
    all_analyses = []
    for i in range(0, len(posts), BATCH_SIZE):
        batch = posts[i:i + BATCH_SIZE]
        print(f"[analyze] batch {i//BATCH_SIZE + 1}/{-(-len(posts)//BATCH_SIZE)} ({len(batch)} posts)")
        results = analyze_batch(openai_client, batch, offset=i)
        all_analyses.extend(results)
    return all_analyses


def detect_trends(openai_client: OpenAI, analyses: list, posts: list, history: list) -> list:
    if not analyses:
        return []

    history_topics = [h["topic"] for h in history]

    payload = {
        "posts_today": [
            {
                "index": a.get("index", i),
                "trend_tags": a.get("trend_tags", []),
                "account": posts[i].get("account_label") if i < len(posts) else "",
                "engagement": posts[i].get("engagement_score", 0) if i < len(posts) else 0,
            }
            for i, a in enumerate(analyses)
        ],
        "history_topics_7d": history_topics,
    }

    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": TREND_SYSTEM},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        response_format={"type": "json_object"},
    )
    data = json.loads(response.choices[0].message.content)
    return data.get("clusters") or []


def run(posts: list | None = None):
    db = get_client()
    openai_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    if posts is None:
        posts = get_posts_today(db)

    if not posts:
        print("[analyze] no posts today, skipping")
        return

    history = get_trend_history(db, days=7)
    history_avg = build_history_avg(history)

    # Stage 1 — per-post summaries in batches of 5
    analyses = analyze_posts_batched(openai_client, posts)

    for analysis in analyses:
        idx = analysis.get("index")
        if idx is None or idx >= len(posts):
            continue
        post = posts[idx]
        post_db_id = post.get("id") or post.get("db_id")
        if not post_db_id:
            continue
        insert_summary(
            db, post_db_id,
            summary_pl=analysis.get("summary_pl", ""),
            trend_tags=analysis.get("trend_tags", []),
            hook_type=analysis.get("hook_type", ""),
        )
        if analysis.get("hook_text"):
            insert_hook(
                db, post_db_id,
                hook_text=analysis["hook_text"],
                hook_type=analysis.get("hook_type", ""),
                why_it_works=analysis.get("why_it_works", ""),
            )

    # Stage 2 — trend clustering on tags only
    clusters = detect_trends(openai_client, analyses, posts, history)

    for cluster in clusters:
        post_indices = cluster.get("post_indices", [])
        post_ids = [
            posts[i].get("id") or posts[i].get("db_id")
            for i in post_indices if i < len(posts)
        ]
        total_engagement = cluster.get("total_engagement", 0)

        # engagement_delta liczymy w Pythonie, nie przez GPT
        delta = compute_delta(cluster["topic"], total_engagement, history_avg)

        upsert_trend_cluster(
            db,
            topic=cluster["topic"],
            status=cluster["status"],
            cross_source_count=cluster.get("cross_source_count", 1),
            total_engagement=total_engagement,
            engagement_delta=delta,
            post_ids=[pid for pid in post_ids if pid],
        )

    print(f"[analyze] analyzed {len(analyses)} posts, {len(clusters)} trend clusters")


if __name__ == "__main__":
    run()
