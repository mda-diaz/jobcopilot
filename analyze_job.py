import os
import re
import sys
from datetime import date
from pathlib import Path

import requests
import yaml
from bs4 import BeautifulSoup
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR / "src"))

load_dotenv(BASE_DIR / ".env")

DIGESTS_DIR = BASE_DIR / "data" / "digests"


def fetch_job_description(url):
    """Fetch job description from URL. Falls back to manual paste for LinkedIn."""
    is_linkedin = "linkedin.com" in url.lower()

    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, "html.parser")

        # Remove script, style, nav, header, footer noise
        for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
            tag.decompose()

        text = soup.get_text(separator="\n")
        text = "\n".join(line.strip() for line in text.splitlines() if line.strip())

        # LinkedIn login wall detection
        if is_linkedin and (
            "join linkedin" in text.lower()
            or "sign in" in text.lower()[:500]
            or len(text) < 300
        ):
            raise ValueError("LinkedIn login wall detected")

        return text

    except ValueError:
        print("Could not fetch LinkedIn URL automatically.")
        print("Please paste the job description below, then press Enter twice:")
        lines = []
        while True:
            line = input()
            if line == "":
                break
            lines.append(line)
        return "\n".join(lines)

    except Exception as e:
        print(f"Warning: could not fetch URL ({e})")
        print("Please paste the job description below, then press Enter twice:")
        lines = []
        while True:
            line = input()
            if line == "":
                break
            lines.append(line)
        return "\n".join(lines)


def load_cv():
    cv_path = BASE_DIR / "config" / "cv_template.md"
    if cv_path.exists():
        return cv_path.read_text(encoding="utf-8")

    pdf_path = BASE_DIR / "config" / "cv.pdf"
    if pdf_path.exists():
        from pdfminer.high_level import extract_text
        text = extract_text(str(pdf_path))
        cv_path.write_text(text, encoding="utf-8")
        return text

    print("Warning: no CV found at config/cv_template.md or config/cv.pdf")
    return ""


def load_profile():
    with open(BASE_DIR / "config" / "profile.yaml") as f:
        return yaml.safe_load(f)


def call_llm(job_description, cv_text):
    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        raise RuntimeError("OPENAI_API_KEY not set in .env.")

    from openai import OpenAI
    client = OpenAI(api_key=openai_key)

    system = "You are an expert CV coach and ATS specialist. Be specific and actionable."
    user_content = f"""JOB POSTING:
{job_description[:4000]}

CANDIDATE CV:
{cv_text[:4000]}

Analyze the gap between this CV and the job posting. Produce a report with:

## Match score: X/100

## Keywords missing from CV
List exact keywords and phrases from the job description that are absent from the CV but should be added. These are what ATS systems filter on.

## CV sections to update
For each section of the CV that should change, explain:
- What to change
- Why (what the job is looking for)
- Suggested rewrite (show the actual new text)

## Red flags
Anything in the CV that might cause automatic rejection for this role.

## What you already have
Skills and experience that directly match — so the candidate knows what to highlight in interviews."""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=2048,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
    )
    return response.choices[0].message.content


def slugify(text):
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text[:40]


def extract_company_from_url(url):
    """Best-effort company name from URL domain."""
    try:
        domain = url.split("//")[-1].split("/")[0]
        domain = domain.replace("www.", "").split(".")[0]
        return domain
    except Exception:
        return "unknown"


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 analyze_job.py <job_url>")
        sys.exit(1)

    job_url = sys.argv[1]
    today = date.today().isoformat()
    DIGESTS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Fetching job description from: {job_url}")
    job_description = fetch_job_description(job_url)
    if not job_description.strip():
        print("Error: no job description text found. Exiting.")
        sys.exit(1)
    print(f"Fetched {len(job_description)} characters of job text.")

    cv_text = load_cv()
    if not cv_text:
        print("Error: no CV found. Add config/cv_template.md or config/cv.pdf first.")
        sys.exit(1)

    company = extract_company_from_url(job_url)

    print("Running gap analysis...")
    report = call_llm(job_description, cv_text)

    # Save gap analysis report
    report_path = DIGESTS_DIR / f"gap_analysis_{company}_{today}.md"
    report_path.write_text(f"# Gap Analysis — {company} — {today}\n\nJob URL: {job_url}\n\n{report}", encoding="utf-8")
    print(f"\nReport saved to {report_path}\n")
    print("=" * 60)
    print(report)
    print("=" * 60)

    # Produce tailored CV
    print("\nGenerating tailored CV...")
    import tailor
    job_dict = {
        "title": "Role from gap analysis",
        "company": company,
        "description": job_description,
    }
    cv_out = tailor.tailor_cv(job_dict)

    # Rename to cv_tailored_ prefix
    if cv_out:
        tailored_path = DIGESTS_DIR / f"cv_tailored_{company}_{today}.md"
        Path(cv_out).rename(tailored_path)
        print(f"Tailored CV saved to {tailored_path}")


if __name__ == "__main__":
    main()
