"""
Claude Sonnet 4.6 — fact-check and hype detection for trend clusters.
Flags AI hype claims and verifies against official sources.
"""
import json
import os
import anthropic
from db.queries import get_client, get_today_clusters

SYSTEM = """Jesteś ekspertem AI i fact-checkerem. Sprawdzasz czy twierdzenia o modelach AI i narzędziach są rzetelne.

Dla każdego klastra trendów zwróć obiekt z polami:
- topic: bez zmian
- verdict: "verified" | "mixed" | "hype" | "unverifiable"
  verified = twierdzenia zgodne z oficjalnymi źródłami
  mixed = część prawdziwa, część przesadzona
  hype = typowe AI hype bez pokrycia ("100x szybszy", "AGI", przesadzone benchmarki)
  unverifiable = brak wystarczających danych do oceny
- note_pl: 1-2 zdania po polsku z wyjaśnieniem werdyktu
- hype_flags: lista konkretnych fraz które są przesadzone (może być pusta lista)

Odpowiedz TYLKO poprawnym JSON: {"clusters": [...]}
"""


def run():
    db = get_client()
    claude = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    clusters = get_today_clusters(db)
    if not clusters:
        print("[verify] no clusters today")
        return

    payload = [
        {"topic": c["topic"], "status": c["status"],
         "cross_source_count": c["cross_source_count"],
         "total_engagement": c["total_engagement"]}
        for c in clusters
    ]

    response = claude.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        messages=[
            {"role": "user", "content": f"{SYSTEM}\n\nKlastry:\n{json.dumps(payload, ensure_ascii=False)}"},
        ],
    )

    text = response.content[0].text
    start = text.find("{")
    end = text.rfind("}") + 1
    data = json.loads(text[start:end])

    for item in data.get("clusters", []):
        matching = [c for c in clusters if c["topic"] == item["topic"]]
        for cluster in matching:
            db.table("trend_clusters").update({
                "status": f"{cluster['status']}_{item['verdict']}",
            }).eq("id", cluster["id"]).execute()

    print(f"[verify] verified {len(data.get('clusters', []))} clusters")


if __name__ == "__main__":
    run()
