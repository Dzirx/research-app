"""
Orchestrator — runs the full daily pipeline.
Called by cron at 04:30 (scraping) and chained steps thereafter.
Can also be run manually: python main.py
"""
import sys
from dotenv import load_dotenv
load_dotenv()

from scrapers import social, rss
from processing import transcribe, analyze, enrich_articles, verify
from report import generate
from send import send_report


def run_pipeline():
    print("=== AI Creator Report Pipeline START ===")

    # 1. Scrape social media
    print("\n[1/7] Scraping social media...")
    posts = social.run()

    # 2. Transcribe IG Reels
    print("\n[2/7] Transcribing videos...")
    posts = transcribe.run(posts)

    # 3. Scrape RSS / newsletters
    print("\n[3/7] Scraping RSS feeds...")
    rss.run()

    # 4. Analyze posts + detect trends
    print("\n[4/7] Analyzing posts & detecting trends...")
    analyze.run(posts)

    # 5. Enrich articles with Polish summaries
    print("\n[5/7] Enriching articles...")
    enrich_articles.run()

    # 6. Verify trends (Claude fact-check)
    print("\n[6/7] Verifying trends...")
    verify.run()

    # 7. Generate PDF
    print("\n[7/7] Generating report...")
    pdf_path, meta = generate.run()

    # Send
    send_report(pdf_path, None, meta["report_id"])

    print("\n=== Pipeline DONE ===")


if __name__ == "__main__":
    run_pipeline()
