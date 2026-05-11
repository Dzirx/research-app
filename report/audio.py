"""Generates Polish audio summary using edge-tts."""
import asyncio
import os
from datetime import date
from pathlib import Path
import edge_tts
from db.queries import get_client, get_today_clusters


VOICE = "pl-PL-MarekNeural"


def build_summary_text(clusters: list, report_date: str) -> str:
    lines = [f"Dzienny raport AI z {report_date}. "]
    breaking = [c for c in clusters if "breaking" in c["status"]]
    trending = [c for c in clusters if "trending" in c["status"]]
    if breaking:
        topics = ", ".join(c["topic"] for c in breaking[:3])
        lines.append(f"Dzisiaj pojawiły się nowe tematy: {topics}. ")
    if trending:
        topics = ", ".join(c["topic"] for c in trending[:3])
        lines.append(f"Rosnące trendy to: {topics}. ")
    if not breaking and not trending:
        lines.append("Dziś bez przełomowych nowości. Spokojny dzień w AI. ")
    lines.append("Pełny raport w załączonym PDF-ie. Dobrego dnia!")
    return "".join(lines)


async def synthesize(text: str, output_path: str):
    communicate = edge_tts.Communicate(text, VOICE)
    await communicate.save(output_path)


def run(context: dict | None = None) -> str:
    db = get_client()
    clusters = context.get("context", {}).get("trend_clusters") if context else None
    if clusters is None:
        clusters = get_today_clusters(db)

    report_date = date.today().strftime("%d.%m.%Y")
    text = build_summary_text(clusters, report_date)

    output_dir = Path(os.environ.get("REPORT_OUTPUT_DIR", "/tmp/reports"))
    output_dir.mkdir(parents=True, exist_ok=True)
    audio_path = str(output_dir / f"ai_report_{date.today().isoformat()}.mp3")

    asyncio.run(synthesize(text, audio_path))
    print(f"[audio] saved: {audio_path}")
    return audio_path


if __name__ == "__main__":
    run()
