"""
Generates the daily PDF report and video scripts using GPT-4o mini + Jinja2 + Playwright.
"""
import json
import os
from datetime import date
from pathlib import Path
import psycopg2.extras
from jinja2 import Environment, FileSystemLoader
from playwright.sync_api import sync_playwright
from openai import OpenAI
from db.queries import (
    get_client, get_posts_today, get_today_clusters,
    get_articles_today, get_top_posts_today, get_hooks_today, save_report,
)

SCRIPTS_SYSTEM = """Jesteś ekspertem content creatorów AI. Na podstawie podanych trendów napisz 3 gotowe skrypty wideo.
Każdy skrypt ma temat z listy trendów "breaking" lub "trending".
Format JSON: {"scripts": [{"topic": "...", "hook": "...", "body": "...", "cta": "..."}]}
Hook = pierwsze 5 sekund które zatrzymują scrollowanie.
Body = 3-4 zdania wartościowej treści.
CTA = wezwanie do działania (follow, komentarz, save).
Pisz po polsku, w stylu naturalnym twórcy AI.
"""


def generate_scripts(openai_client: OpenAI, clusters: list) -> list:
    trending = [c for c in clusters if "breaking" in c["status"] or "trending" in c["status"]]
    if not trending:
        trending = clusters[:3]
    if not trending:
        return []
    payload = [{"topic": c["topic"], "engagement": c["total_engagement"]} for c in trending[:5]]
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SCRIPTS_SYSTEM},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        response_format={"type": "json_object"},
    )
    data = json.loads(response.choices[0].message.content)
    return data.get("scripts", [])


def render_html(context: dict) -> str:
    template_dir = Path(__file__).parent / "templates"
    env = Environment(loader=FileSystemLoader(str(template_dir)))
    template = env.get_template("report.html")
    return template.render(**context)


def html_to_pdf(html: str, output_path: str):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(html, wait_until="networkidle")
        page.pdf(
            path=output_path,
            format="A4",
            margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
            print_background=True,
        )
        browser.close()


def build_context(db, openai_client: OpenAI, report_date: str) -> dict:
    posts = get_posts_today(db)
    clusters = get_today_clusters(db)
    articles = get_articles_today(db)
    top_posts_raw = get_top_posts_today(db, limit=3)
    hooks = get_hooks_today(db)
    scripts = generate_scripts(openai_client, clusters)

    top_posts = top_posts_raw

    # attach summaries to social posts (first 20 for diary section)
    social_posts = []
    with db.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        for post in sorted(posts, key=lambda p: p.get("engagement_score", 0), reverse=True)[:20]:
            cur.execute("SELECT summary_pl FROM summaries WHERE post_id = %s LIMIT 1", (post["id"],))
            row = cur.fetchone()
            post["summary_pl"] = row["summary_pl"] if row else None
            social_posts.append(post)

    return {
        "date": report_date,
        "social_posts": social_posts,
        "trend_clusters": clusters,
        "top_posts": top_posts,
        "articles": articles,
        "video_scripts": scripts,
        "hooks": hooks,
    }


def run() -> tuple[str, dict]:
    db = get_client()
    openai_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    report_date = date.today().strftime("%d.%m.%Y")

    output_dir = Path(os.environ.get("REPORT_OUTPUT_DIR", "/tmp/reports"))
    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = str(output_dir / f"ai_report_{date.today().isoformat()}.pdf")

    context = build_context(db, openai_client, report_date)
    html = render_html(context)
    html_to_pdf(html, pdf_path)

    report_id = save_report(db, pdf_path=pdf_path, audio_path=None)
    print(f"[generate] PDF saved: {pdf_path} (report_id={report_id})")
    return pdf_path, {"report_id": report_id, "context": context}


if __name__ == "__main__":
    run()
