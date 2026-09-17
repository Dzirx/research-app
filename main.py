"""
Orchestrator — runs the full daily pipeline.
Called by cron at 04:30 (scraping) and chained steps thereafter.
Can also be run manually: python main.py
"""
import sys
from dotenv import load_dotenv
load_dotenv()

from scrapers import social
from processing import transcribe, analyze, check_published, verify
from report import generate
from send import send_report


def run_pipeline():
    print("=== AI Creator Report Pipeline START ===")

    # 1. Scrape social media (+ own account, do wykrywania publikacji)
    print("\n[1/6] Scraping social media...")
    posts = social.run()

    # 2. Transcribe IG Reels
    print("\n[2/6] Transcribing videos...")
    posts = transcribe.run(posts)

    # 3. Analyze posts + detect trends
    print("\n[3/6] Analyzing posts & detecting trends...")
    analyze.run(posts)

    # 4. Mark proposed script ideas as published if they show up on own account
    print("\n[4/6] Checking which script ideas got published...")
    check_published.run()

    # 5. Verify trends (Claude fact-check)
    print("\n[5/6] Verifying trends...")
    verify.run()

    # 6. Generate PDF
    print("\n[6/6] Generating report...")
    pdf_path, meta = generate.run()

    # Send
    send_report(pdf_path, None, meta["report_id"])

    print("\n=== Pipeline DONE ===")


if __name__ == "__main__":
    run_pipeline()
