"""Downloads and transcribes IG video posts via OpenAI Whisper."""
import os
import re
import tempfile
import httpx
from openai import OpenAI
from db.queries import get_client, get_posts_today, insert_transcription

# Whisper bez kontekstu gubi terminologię — w produkcji zrobił z "AI" konsekwentne "EA"
# ("zaczynałam od zera w EA", "sposobem EA Native"). Prompt naprowadza go na słownictwo,
# które w tych rolkach pada najczęściej.
WHISPER_PROMPT = (
    "AI, sztuczna inteligencja, Claude, Claude Code, ChatGPT, GPT, Codex, LLM, "
    "agent AI, n8n, automatyzacja, workflow, prompt, API, Notion, DevOps."
)

# Whisper na ciszy/muzyce halucynuje napisy końcowe z materiałów treningowych.
# Takie "transkrypcje" trafiały do analizy jako treść merytoryczna.
_HALLUCINATION_PATTERNS = [
    r"amara\.org",
    r"napisy stworzone przez",
    r"napisy: ",
    r"zapraszam do subskrypcji",
    r"dziękuję za uwagę",
    r"dzięki za obejrzenie",
    r"subscribe to our channel",
]
MIN_TRANSCRIPT_LEN = 25


def download_video(video_url: str, dest_path: str):
    with httpx.stream("GET", video_url, follow_redirects=True, timeout=60) as r:
        r.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in r.iter_bytes(chunk_size=8192):
                f.write(chunk)


def transcribe_audio(openai_client: OpenAI, audio_path: str) -> str:
    with open(audio_path, "rb") as f:
        result = openai_client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            language="pl",
            prompt=WHISPER_PROMPT,
        )
    return result.text


def is_usable_transcript(transcript: str) -> bool:
    text = (transcript or "").strip()
    if len(text) < MIN_TRANSCRIPT_LEN:
        return False
    lowered = text.lower()
    return not any(re.search(p, lowered) for p in _HALLUCINATION_PATTERNS)


def run(posts: list | None = None):
    db = get_client()
    openai_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    if posts is None:
        # Uwaga: baza nie przechowuje video_url, więc uruchomienie tego kroku samodzielnie
        # nic nie zrobi — transkrypcja działa w ramach pełnego pipeline'u (main.py).
        posts = get_posts_today(db)

    transcribed = 0
    skipped = 0
    for post in posts:
        video_url = post.get("video_url")
        if not video_url:
            continue
        try:
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=True) as tmp:
                download_video(video_url, tmp.name)
                transcript = transcribe_audio(openai_client, tmp.name)
        except Exception as e:
            print(f"[transcribe] ERROR {post.get('url')}: {e}")
            continue

        if not is_usable_transcript(transcript):
            print(f"[transcribe] odrzucam pustą/halucynowaną transkrypcję: {post.get('url')}")
            skipped += 1
            continue

        transcript = transcript.strip()
        insert_transcription(db, post.get("id") or post["db_id"], transcript)
        # Transkrypcja płynie dalej OSOBNYM polem. Doklejanie jej do content sprawiało,
        # że model widział jeden blok tekstu i streszczał caption zamiast merytoryki.
        post["transcript"] = transcript
        transcribed += 1

    print(f"[transcribe] transcribed {transcribed} videos, odrzucono {skipped}")
    return posts


if __name__ == "__main__":
    run()
