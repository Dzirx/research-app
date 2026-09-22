"""
Generates the daily PDF report and video scripts using Jinja2 + Playwright.
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
    get_cluster_source_material, get_recent_script_ideas,
    insert_script_idea, save_report,
)

SCRIPT_TRANSCRIPT_LIMIT = 1500
MAX_POSTS_PER_CLUSTER = 2
MAX_CLUSTERS_FOR_SCRIPTS = 5

SCRIPTS_SYSTEM_TEMPLATE = """Jesteś ekspertem content creatorów AI. Na podstawie MATERIAŁU ŹRÓDŁOWEGO
poniżej napisz 3 gotowe skrypty wideo dopasowane do profilu marki.

PROFIL MARKI:
{brand_profile}

JUŻ ZAPROPONOWANE / OPUBLIKOWANE POMYSŁY (ostatnie 60 dni) — NIE POWTARZAJ tych samych
motywów, metafor ani scen:
{used_ideas}

ZASADA NADRZĘDNA: każdy skrypt musi wyrastać z KONKRETU, który realnie pada w materiale
źródłowym (pole "materialy": podsumowanie, konkrety, transkrypcja). Nie wymyślaj scenariuszy,
narzędzi ani sytuacji, których w materiale nie ma. Materiał to obserwacja cudzej rolki —
bierzesz z niej mechanizm i przekładasz na własny przykład z profilu marki.
Jeśli materiał nie zawiera żadnego konkretu, pomiń ten temat i weź następny.
Nie podawaj liczb, oszczędności ani wyników wdrożeń, których w materiale nie ma —
gdy brakuje konkretu, opisz mechanizm, nie rezultat.

Format JSON: {{"scripts": [{{"topic": "...", "hook": "...", "body": "...", "cta": "...",
"zrodlo_url": "...", "co_z_materialu": "..."}}]}}
Hook = pierwsze 5 sekund które zatrzymują scrollowanie.
Body = 3-4 zdania wartościowej treści.
CTA = wezwanie do działania — zgodnie z zasadą CTA z profilu marki (nie na siłę do każdej scenki).
zrodlo_url = URL posta z "materialy", na którym stoi ten skrypt.
co_z_materialu = jedno zdanie: która obserwacja ze źródła jest podstawą tego skryptu.
Pisz po polsku, w stylu z profilu marki.
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


def build_scripts_payload(db, clusters: list) -> list:
    """Do promptu idzie materiał źródłowy klastra, nie sama nazwa tematu."""
    payload = []
    for cluster in clusters:
        material = get_cluster_source_material(db, cluster.get("post_ids") or [])
        if not material:
            continue
        payload.append({
            "topic": cluster["topic"],
            "engagement": cluster["total_engagement"],
            "materialy": [
                {
                    "konto": m.get("account_label"),
                    "url": m.get("url"),
                    "hook": m.get("hook_text") or "",
                    "podsumowanie": m.get("summary_pl") or "",
                    "konkrety": m.get("key_points") or [],
                    "transkrypcja": (m.get("transcript") or "")[:SCRIPT_TRANSCRIPT_LIMIT],
                }
                for m in material[:MAX_POSTS_PER_CLUSTER]
            ],
        })
    return payload


def generate_scripts(openai_client: OpenAI, clusters: list, db) -> list:
    trending = [c for c in clusters if c["status"] in ("breaking", "trending")]
    if not trending:
        trending = clusters[:3]
    if not trending:
        return []

    payload = build_scripts_payload(db, trending[:MAX_CLUSTERS_FOR_SCRIPTS])
    if not payload:
        print("[generate] brak materiału źródłowego dla klastrów — pomijam skrypty")
        return []

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
            source_url=script.get("zrodlo_url", ""),
            source_note=script.get("co_z_materialu", ""),
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

    # Trend potwierdzony to taki, o którym mówi więcej niż jedno konto. Reszta to
    # pojedyncze sygnały — wcześniej trafiały do raportu jako "BREAKING · 1 źródeł".
    confirmed = [c for c in clusters if (c.get("cross_source_count") or 1) >= 2]
    single = [c for c in clusters if (c.get("cross_source_count") or 1) < 2]

    # attach summaries to social posts (first 20 for diary section)
    social_posts = []
    for post in sorted(posts, key=lambda p: p.get("engagement_score", 0), reverse=True)[:20]:
        post["summary_pl"] = get_post_summary(db, post["id"])
        social_posts.append(post)

    return {
        "date": report_date,
        "social_posts": social_posts,
        "trend_clusters": clusters,
        "confirmed_trends": confirmed,
        "single_signals": single,
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
