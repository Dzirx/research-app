"""Sends the daily report via e-mail (SMTP)."""
import os
import smtplib
from dotenv import load_dotenv
load_dotenv()
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from datetime import date
from db.queries import get_client, mark_report_sent


def send_report(pdf_path: str, audio_path: str | None, report_id: int):
    smtp_host = os.environ["SMTP_HOST"]
    smtp_port = int(os.environ.get("SMTP_PORT", 587))
    smtp_user = os.environ["SMTP_USER"]
    smtp_pass = os.environ["SMTP_PASS"]
    recipient = os.environ["REPORT_RECIPIENT"]

    report_date = date.today().strftime("%d.%m.%Y")
    msg = MIMEMultipart()
    msg["From"] = smtp_user
    msg["To"] = recipient
    msg["Subject"] = f"🤖 AI Creator Report — {report_date}"

    body = f"""Cześć!

W załączniku znajdziesz dzienny raport AI Creator Intelligence z {report_date}.

Co w środku:
I.   Dziennik AI Social — posty z ostatnich 24h
II.  Radar Nowości AI — co się dzieje w branży
III. Top 3 Posty + analiza viralności
IV.  Newslettery & Blogi AI
V.   Gotowe Skrypty Wideo (3 gotowe do nagrania)
VI.  Baza Hooków AI

Miłej lektury! 🚀
"""
    msg.attach(MIMEText(body, "plain", "utf-8"))

    for path in [pdf_path, audio_path]:
        if not path:
            continue
        with open(path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="{os.path.basename(path)}"')
        msg.attach(part)

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)

    db = get_client()
    mark_report_sent(db, report_id)
    print(f"[send] report sent to {recipient}")


if __name__ == "__main__":
    import sys
    pdf = sys.argv[1] if len(sys.argv) > 1 else None
    if not pdf:
        print("Usage: python send.py <pdf_path> <report_id>")
        sys.exit(1)
    report_id = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    send_report(pdf, None, report_id)
