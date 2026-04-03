import json
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent.parent
load_dotenv(BASE_DIR / ".env")


def load_config():
    with open(BASE_DIR / "config" / "profile.yaml") as f:
        return yaml.safe_load(f)


def build_prompt(profile_str, work_mode_str, job):
    description = (job.get("description") or "")[:2000]
    user_content = f"""USER PROFILE:
{profile_str}
Preferred work mode: {work_mode_str}

WORK MODE RULES:
- User accepts: Spain-based (any city), remote from anywhere in Europe
- If job is fully remote and open to European candidates: do not penalize for location
- If job requires presence in a specific non-Spanish city with no remote option: apply -20 score penalty
- If job description mentions "remote", "remoto", "full remote", or "work from anywhere in Europe": treat location as Spain-compatible
- "remote" or "remoto" in the title or description are positive signals: increase score by up to +10

JOB:
Title: {job.get("title", "")}
Company: {job.get("company", "")}
Location: {job.get("location", "")}
Remote: {"yes" if job.get("remote") else "no"}
Description: {description}

Score this job from 0-100 based on fit with the profile.
Consider: skills match, seniority, industry, location, work mode, deal-breakers, and the work mode rules above.

Respond ONLY in this JSON format:
{{
  "score": <int 0-100>,
  "reason": "<exactly 2 sentences explaining the score>",
  "flags": ["<red flag 1>", "<red flag 2>"]
}}"""
    return user_content


def call_llm(profile_str, work_mode_str, job):
    system = "You are a career advisor evaluating job fit. Respond only in valid JSON."
    user_content = build_prompt(profile_str, work_mode_str, job)

    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        raise RuntimeError("OPENAI_API_KEY not set in .env.")

    from openai import OpenAI
    client = OpenAI(api_key=openai_key)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=512,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
    )
    return response.choices[0].message.content


def parse_response(raw):
    try:
        # Strip markdown code fences if the model wraps its response
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text)
    except Exception:
        return {"score": 0, "reason": "parse error", "flags": []}


HR_TITLE_KEYWORDS = [
    "human resources", "recursos humanos", "hr ", " hr", "hrbp",
    "people", "talent", "talento", "rrhh", "relaciones laborales",
    "labour", "labor", "payroll", "nóminas", "nominas",
    "onboarding", "recruiting", "reclutamiento", "people ops",
    "people partner", "hr manager", "hr generalist", "hr analyst",
    "hr operations", "hr director", "hr coordinator",
    "generalista", "analista de personas", "gestión de personas",
]


def is_hr_relevant(title):
    title_lower = title.lower()
    return any(kw in title_lower for kw in HR_TITLE_KEYWORDS)


ON_SITE_PENALTIES = ["presencial", "100% on-site"]
REMOTE_SIGNALS = ["remote", "remoto", "full remote", "work from anywhere", "teletrabajo"]


def apply_penalties(job, score, flags):
    flags = list(flags)
    description = (job.get("description") or "").lower()
    title = (job.get("title") or "").lower()
    text = title + " " + description

    # Hard cap for on-site deal-breakers
    for phrase in ON_SITE_PENALTIES:
        if phrase in text:
            if score > 40:
                flags.append(f"On-site penalty: '{phrase}' detected — score capped at 40")
                score = 40
            break

    # Remote bonus: +10 if already flagged remote or remote signal in text, cap at 100
    is_remote = job.get("remote") or any(s in text for s in REMOTE_SIGNALS)
    if is_remote and score <= 90:
        score = min(score + 10, 100)

    return score, flags


def score_jobs(jobs):
    config = load_config()
    profile_str = yaml.dump(config, allow_unicode=True)
    work_mode_str = " or ".join(config.get("work_mode", ["remote", "hybrid"]))
    min_score = config.get("min_score", 60)

    scored = []
    title_rejected = 0

    for job in jobs:
        if not is_hr_relevant(job.get("title", "")):
            job["score"] = 0
            job["reason"] = "Job title not related to HR"
            job["flags"] = ["irrelevant role"]
            scored.append(job)
            title_rejected += 1
            continue

        try:
            raw = call_llm(profile_str, work_mode_str, job)
            result = parse_response(raw)
        except Exception as e:
            print(f"[score] Error scoring '{job.get('title')}' at '{job.get('company')}': {e}")
            result = {"score": 0, "reason": "scoring error", "flags": []}

        score, flags = apply_penalties(job, int(result.get("score", 0)), result.get("flags", []))
        job["score"] = score
        job["reason"] = result.get("reason", "")
        job["flags"] = flags
        scored.append(job)

    print(f"  Title filter rejected {title_rejected} jobs before LLM scoring")
    scored.sort(key=lambda j: j["score"], reverse=True)
    return scored, min_score


def main():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from fetch import fetch_new_jobs

    jobs = fetch_new_jobs()
    print(f"Scoring {len(jobs)} new jobs...")

    results = score_jobs(jobs)
    print(f"\nJobs above min_score threshold: {len(results)}\n")

    for job in results[:5]:
        print(f"[{job['score']}] {job['title']} @ {job['company']} ({job['location']})")
        print(f"  {job['reason']}")
        if job["flags"]:
            print(f"  Flags: {', '.join(job['flags'])}")
        print(f"  {job['url']}\n")


if __name__ == "__main__":
    main()
