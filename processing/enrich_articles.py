"""Summarizes RSS articles to Polish bullet points using GPT-4o mini."""
import json
import os
from openai import OpenAI
from db.queries import get_client, get_articles_today

SYSTEM = """Jesteś analitykiem AI. Dla każdego artykułu zwróć obiekt z polami:
- id: id artykułu (bez zmian)
- summary_pl: 2-4 bullet pointy po polsku z najważniejszymi informacjami (format: "• ...")
- category: jeden z: new_model | new_tool | research | company_update | tutorial | opinion
- importance: "game-changer" | "incremental" | "hype"
Odpowiedz TYLKO poprawnym JSON: {"articles": [...]}
"""


def enrich(openai_client: OpenAI, articles: list) -> list:
    if not articles:
        return []
    payload = [
        {"id": a["id"], "title": a["title"], "content": (a.get("content") or "")[:2000]}
        for a in articles
    ]
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        response_format={"type": "json_object"},
    )
    data = json.loads(response.choices[0].message.content)
    return data.get("articles", [])


def run():
    db = get_client()
    openai_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    articles = get_articles_today(db)
    if not articles:
        print("[enrich] no articles today")
        return

    enriched = enrich(openai_client, articles)
    with db.cursor() as cur:
        for item in enriched:
            cur.execute(
                "UPDATE articles SET summary_pl = %s WHERE id = %s",
                (item.get("summary_pl", ""), item["id"]),
            )
    db.commit()

    print(f"[enrich] enriched {len(enriched)} articles")


if __name__ == "__main__":
    run()
