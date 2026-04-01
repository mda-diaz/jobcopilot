import os
import re
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent.parent
load_dotenv(BASE_DIR / ".env")

CV_TEMPLATE = BASE_DIR / "config" / "cv_template.md"
CV_PDF = BASE_DIR / "config" / "cv.pdf"
DIGESTS_DIR = BASE_DIR / "data" / "digests"


def extract_pdf_text(pdf_path):
    from pdfminer.high_level import extract_text
    return extract_text(str(pdf_path))


def ensure_cv_template():
    if CV_TEMPLATE.exists():
        return CV_TEMPLATE.read_text(encoding="utf-8")

    if CV_PDF.exists():
        print("[tailor] cv_template.md not found — extracting text from cv.pdf...")
        text = extract_pdf_text(CV_PDF)
        CV_TEMPLATE.write_text(text, encoding="utf-8")
        print(f"[tailor] Saved extracted CV to {CV_TEMPLATE}")
        return text

    print("[tailor] Warning: neither config/cv_template.md nor config/cv.pdf found. Returning empty strings.")
    return ""


def slugify(text):
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text[:40]


def call_llm(cv_text, job):
    description = (job.get("description") or "")[:2000]
    system = "You are an expert CV writer. Respond only with the full rewritten CV in markdown. Do not add any explanation."
    user_content = f"""BASE CV:
{cv_text}

TARGET JOB:
Title: {job.get("title", "")}
Company: {job.get("company", "")}
Description: {description}

Rewrite the CV summary and the top 3 bullet points under each role to better match this job.
Rules:
- Mirror keywords from the job description naturally
- Do not invent experience that does not exist in the base CV
- Keep total length and structure identical to the original
- Return the complete CV in markdown"""

    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        raise RuntimeError("OPENAI_API_KEY not set in .env.")

    from openai import OpenAI
    client = OpenAI(api_key=openai_key)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=4096,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
    )
    return response.choices[0].message.content


def tailor_cv(job):
    cv_text = ensure_cv_template()
    if not cv_text:
        return ""

    tailored = call_llm(cv_text, job)

    company_slug = slugify(job.get("company") or "unknown")
    today = date.today().isoformat()
    filename = f"cv_{company_slug}_{today}.md"
    output_path = DIGESTS_DIR / filename

    DIGESTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path.write_text(tailored, encoding="utf-8")
    print(f"[tailor] Saved tailored CV to {output_path}")

    return str(output_path)


def main():
    dummy_job = {
        "title": "Senior Product Manager",
        "company": "Acme Corp",
        "location": "Madrid, Spain",
        "description": (
            "We are looking for a Senior Product Manager to lead our fintech product roadmap. "
            "You will work closely with engineering, design, and stakeholders to define strategy "
            "and deliver impactful features. Strong SQL and analytics skills required. "
            "Experience with agile/scrum and a background in fintech or ecommerce is a plus."
        ),
        "score": 85,
        "reason": "Strong skills match on roadmap and analytics. Fintech industry preferred.",
    }

    path = tailor_cv(dummy_job)
    if path:
        print(f"[tailor] Test complete. Output: {path}")
    else:
        print("[tailor] Test skipped — no CV source found.")


if __name__ == "__main__":
    main()
