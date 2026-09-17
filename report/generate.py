"""
Generates the daily PDF report and video scripts using GPT-4o mini + Jinja2 + Playwright.
"""
import json
import os
from datetime import date
from pathlib import Path
import yaml
from jinja2 import Environment, FileSystemLoader
from playwright.sync_api import sync_playwright
from openai import OpenAI
from db.queries import (
    get_client, get_posts_today, get_today_clusters,
    get_top_posts_today, get_hooks_today, get_post_summary,
    get_recent_script_ideas, insert_script_idea, save_report,
)

SCRIPTS_SYSTEM_TEMPLATE = """Jesteś ekspertem content creatorów AI. Na podstawie podanych trendów napisz 3 gotowe
skrypty wideo dopasowane do profilu marki poniżej.

PROFIL MARKI:
{brand_profile}

JUŻ ZAPROPONOWANE / OPUBLIKOWANE POMYSŁY (ostatnie 60 dni) — NIE POWTARZAJ tych samych
motywów, metafor ani scen:
{used_ideas}

Każdy skrypt ma temat z listy trendów "breaking" lub "trending".
Format JSON: {{"scripts": [{{"topic": "...", "hook": "...", "body": "...", "cta": "..."}}]}}
Hook = pierwsze 5 sekund które zatrzymują scrollowanie.
Body = 3-4 zdania wartościowej treści.
CTA = wezwanie do działania — zgodnie z zasadą CTA z profilu marki (nie na siłę do każdej scenki).
Pisz po polsku, w stylu ze profilu marki.
"""


def load_brand_profile() -> str:
    path = Path(__file__).parent.parent / "brand_profile.yaml"
    if not path.exists():
        return "(brak brand_profile.yaml — pisz neutralnie, w stylu twórcy AI)"
    with open(path) as f:
        profile = yaml.safe_load(f)
    return yaml.safe_dump(profile, allow_unicode=True, sort_keys=False)


def format_used_ideas(ideas: list) -> str:
    if not ideas:
        return "(brak — to pierwsza paczka skryptów)"
    return "\n".join(f"- {i['topic']}: {i['hook']}" for i in ideas)


def generate_scripts(openai_client: OpenAI, clusters: list, db) -> list:
    trending = [c for c in clusters if "breaking" in c["status"] or "trending" in c["status"]]
    if not trending:
        trending = clusters[:3]
    if not trending:
        return []
    payload = [{"topic": c["topic"], "engagement": c["total_engagement"]} for c in trending[:5]]

    system = SCRIPTS_SYSTEM_TEMPLATE.format(
        brand_profile=load_brand_profile(),
        used_ideas=format_used_ideas(get_recent_script_ideas(db, days=60)),
    )

    response = openai_client.chat.completions.create(
        model="gpt-5.6-sol",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        response_format={"type": "json_object"},
    )
    data = json.loads(response.choices[0].message.content)
    scripts = data.get("scripts", [])

    for script in scripts:
        insert_script_idea(
            db,
            topic=script.get("topic", ""),
            hook=script.get("hook", ""),
            body=script.get("body", ""),
            cta=script.get("cta", ""),
        )

    return scripts


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
    top_posts = get_top_posts_today(db, limit=3)
    hooks = get_hooks_today(db)
    scripts = generate_scripts(openai_client, clusters, db)

    # attach summaries to social posts (first 20 for diary section)
    social_posts = []
    for post in sorted(posts, key=lambda p: p.get("engagement_score", 0), reverse=True)[:20]:
        post["summary_pl"] = get_post_summary(db, post["id"])
        social_posts.append(post)

    return {
        "date": report_date,
        "social_posts": social_posts,
        "trend_clusters": clusters,
        "top_posts": top_posts,
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
