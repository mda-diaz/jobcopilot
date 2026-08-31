import os
from pathlib import Path

import requests
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent.parent
load_dotenv(BASE_DIR / ".env")

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"
TELEGRAM_MAX_LEN = 4096

MARKDOWN_V2_SPECIAL_CHARS = set(r"_*[]()~`>#+-=|{}.!\\")


def escape_markdown_v2(text):
    return "".join(f"\\{c}" if c in MARKDOWN_V2_SPECIAL_CHARS else c for c in text)


def escape_markdown_v2_url(url):
    return url.replace("\\", "\\\\").replace(")", "\\)")


def format_job_markdown(job):
    score = job.get("score", 0)
    title = escape_markdown_v2(job.get("title") or "")
    company = escape_markdown_v2(job.get("company") or "")
    url = job.get("url") or ""
    link = f"[Aplicar]({escape_markdown_v2_url(url)})" if url else "Sin enlace"
    return f"*{score}/100* — *{title}* @ {company}\n{link}"


def format_job_plain(job):
    score = job.get("score", 0)
    title = job.get("title") or ""
    company = job.get("company") or ""
    url = job.get("url") or "Sin enlace"
    return f"{score}/100 — {title} @ {company}\n{url}"


def chunk_blocks(blocks, separator="\n\n"):
    chunks = []
    current = ""
    for block in blocks:
        candidate = block if not current else current + separator + block
        if len(candidate) > TELEGRAM_MAX_LEN:
            if current:
                chunks.append(current)
            current = block[:TELEGRAM_MAX_LEN]
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def send_message(token, chat_id, text, parse_mode=None):
    payload = {"chat_id": chat_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    response = requests.post(TELEGRAM_API_URL.format(token=token), json=payload, timeout=10)
    response.raise_for_status()


def send_digest(jobs):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("[notify] Warning: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set — skipping Telegram send.")
        return

    if not jobs:
        print("[notify] No jobs to send.")
        return

    try:
        try:
            chunks = chunk_blocks([format_job_markdown(job) for job in jobs])
            for chunk in chunks:
                send_message(token, chat_id, chunk, parse_mode="MarkdownV2")
        except requests.exceptions.RequestException:
            print("[notify] MarkdownV2 send failed — retrying as plain text.")
            chunks = chunk_blocks([format_job_plain(job) for job in jobs])
            for chunk in chunks:
                send_message(token, chat_id, chunk)
        print(f"[notify] Sent digest to Telegram ({len(chunks)} message(s)).")
    except Exception as e:
        print(f"[notify] Error sending Telegram digest: {e}")


def main():
    dummy_jobs = [
        {
            "title": "Senior Product Manager",
            "company": "Acme Fintech",
            "score": 88,
            "url": "https://example.com/job/1",
        },
        {
            "title": "HR Business Partner (Test) — [confidential]",
            "company": "Acme & Co.",
            "score": 74,
            "url": "https://example.com/job/2",
        },
    ]

    send_digest(dummy_jobs)
    print("[notify] Test complete.")


if __name__ == "__main__":
    main()
