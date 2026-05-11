"""Downloads and transcribes IG Reels audio via OpenAI Whisper."""
import os
import tempfile
import httpx
from openai import OpenAI
from db.queries import get_client, get_posts_today, insert_transcription


def download_audio(video_url: str, dest_path: str):
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
        )
    return result.text


def run(posts: list | None = None):
    db = get_client()
    openai_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    if posts is None:
        posts = get_posts_today(db)

    transcribed = 0
    for post in posts:
        video_url = post.get("video_url")
        if not video_url:
            continue
        try:
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=True) as tmp:
                download_audio(video_url, tmp.name)
                transcript = transcribe_audio(openai_client, tmp.name)
            insert_transcription(db, post["id"] if "id" in post else post["db_id"], transcript)
            # enrich content for downstream analysis
            post["content"] = (post.get("content") or "") + "\n\n[TRANSKRYPCJA]: " + transcript
            transcribed += 1
        except Exception as e:
            print(f"[transcribe] ERROR post {post.get('url')}: {e}")

    print(f"[transcribe] transcribed {transcribed} videos")
    return posts


if __name__ == "__main__":
    run()
