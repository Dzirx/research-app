"""
Porównuje wcześniej zaproponowane pomysły na skrypty wideo (script_ideas)
z faktycznie opublikowanymi postami na Twoim własnym koncie (own_posts).
Dzięki temu report/generate.py wie, których motywów NIE powtarzać.
"""
import json
import os
from openai import OpenAI
from db.queries import get_client, get_pending_script_ideas, get_own_posts_recent, mark_script_idea_published

SYSTEM = """Porównujesz pomysły na rolki z faktycznie opublikowanymi postami na Instagramie.
Dla każdego pomysłu sprawdź, czy któryś z opublikowanych postów realizuje ten sam
temat/hook/motyw (nie musi być identyczny tekst — wystarczy ta sama scena/metafora/pointa).
Zwróć TYLKO dopasowania, których jesteś pewien. Format JSON:
{"matches": [{"idea_id": 1, "post_url": "https://..."}]}
Jeśli nic nie pasuje, zwróć {"matches": []}.
"""


def run():
    db = get_client()
    ideas = get_pending_script_ideas(db, days=60)
    posts = get_own_posts_recent(db, days=14)

    if not ideas or not posts:
        print("[check_published] brak pomysłów lub własnych postów do porównania")
        return

    openai_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    payload = {
        "pomysly": [{"idea_id": i["id"], "topic": i["topic"], "hook": i["hook"]} for i in ideas],
        "opublikowane_posty": [
            {"url": p["url"], "content": (p["content"] or "")[:500]} for p in posts
        ],
    }
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        response_format={"type": "json_object"},
    )
    data = json.loads(response.choices[0].message.content)
    matches = data.get("matches", [])

    for match in matches:
        mark_script_idea_published(db, match["idea_id"], match["post_url"])

    print(f"[check_published] oznaczono {len(matches)} pomysłów jako opublikowane")


if __name__ == "__main__":
    run()
