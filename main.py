"""
Orchestrator — runs the full daily pipeline.
Called by cron at 04:30 (scraping) and chained steps thereafter.
Can also be run manually: python main.py
"""
from dotenv import load_dotenv
load_dotenv()

from scrapers import social
from processing import transcribe, analyze, check_published
from report import generate
from send import send_report


def run_pipeline():
    print("=== AI Creator Report Pipeline START ===")

    # 1. Scrape social media (+ own account, do wykrywania publikacji)
    print("\n[1/5] Scraping social media...")
    posts = social.run()

    # Bez nowego materiału raport nie miałby o czym mówić — nie generujemy PDF-u
    # i nie wysyłamy maila. check_published nadrobi przy następnym uruchomieniu.
    if not posts:
        print("\n[pipeline] 0 nowych postów — cisza w eterze, raport nie powstaje.")
        print("=== Pipeline DONE (bez raportu) ===")
        return

    # 2. Transcribe IG Reels
    print("\n[2/5] Transcribing videos...")
    posts = transcribe.run(posts)

    # 3. Analyze posts + detect trends
    print("\n[3/5] Analyzing posts & detecting trends...")
    analyze.run(posts)

    # 4. Mark proposed script ideas as published if they show up on own account
    print("\n[4/5] Checking which script ideas got published...")
    check_published.run()

    # 5. Generate PDF
    print("\n[5/5] Generating report...")
    pdf_path, meta = generate.run()

    # Send
    send_report(pdf_path, None, meta["report_id"])

    print("\n=== Pipeline DONE ===")


if __name__ == "__main__":
    run_pipeline()
