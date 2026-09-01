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
- User accepts: Spain-based (any city, but preference Valencia), remote from anywhere in Europe
- If job is fully remote and open to European candidates: do not penalize for location
- If job requires presence in a specific non-Spanish city with no remote option: apply -20 score penalty
- If job description mentions "remote", "remoto", "full remote", or "work from anywhere in Europe": treat location as Spain-compatible
- "remote" or "remoto" in the title or description are positive signals: increase score by up to +10
- A job located in Valencia is the user's home base — the most convenient option
  available regardless of remote/hybrid/on-site status. Do not apply any on-site
  penalty for a Valencia-based role, and be more flexible on role type/seniority
  fit than you would be for an equivalent job elsewhere

ROLE TYPE RULES:
- User is an HR generalist/HRBP — they work IN HR, not managing payroll departments or leading payroll teams
- If the role is primarily a Payroll Manager, Payroll Lead, or Head of Payroll, score it maximum 30 regardless of other factors
- If the role requires managing a payroll team as main responsibility, apply -30 penalty
- Payroll as a skill used in an HR generalist role is fine and should not be penalized
- HRBP or HR Ops roles that involve moving away from traditional/administrative HR
  tasks toward modernized, data-driven, or AI-enabled ways of working (e.g. people
  analytics, HR technology, process automation, AI-assisted HR tools) are an ideal
  fit — treat this as a strong positive signal and score accordingly
- The title may not say "HR" at all — roles about supporting internal employees or
  external/internal partners in an operations capacity (employee support, partner
  support, shared services, workplace experience, etc.) can be genuine HR/people-ops
  work. Judge these on actual fit with the profile below, not on the title

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
    # Not HR-titled, but often HR/people-ops work in disguise — let these
    # through to the LLM so it can judge fit against the profile instead of
    # rejecting on title alone.
    "employee experience", "employee support", "employee relations",
    "internal support", "partner support", "operations support",
    "workplace experience", "shared services",
]

HR_TITLE_REJECT_KEYWORDS = [
    "payroll manager", "payroll lead", "head of payroll", "payroll team manager",
]


def is_hr_relevant(title):
    title_lower = title.lower()
    if any(kw in title_lower for kw in HR_TITLE_REJECT_KEYWORDS):
        return False
    return any(kw in title_lower for kw in HR_TITLE_KEYWORDS)


ON_SITE_PENALTIES = ["presencial", "100% on-site"]
REMOTE_SIGNALS = ["remote", "remoto", "full remote", "work from anywhere", "teletrabajo"]
VALENCIA_SIGNALS = ["valencia", "valència"]


def apply_penalties(job, score, flags):
    flags = list(flags)
    description = (job.get("description") or "").lower()
    title = (job.get("title") or "").lower()
    location = (job.get("location") or "").lower()
    text = title + " " + description

    is_valencia = any(s in location for s in VALENCIA_SIGNALS)

    # Hard cap for on-site deal-breakers — skip for Valencia, the user's home base,
    # where on-site carries no relocation/commute tradeoff
    if not is_valencia:
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

    # Valencia bonus: +10 for the user's home base, cap at 100. Stacks with the
    # remote bonus above — a remote Valencia-based listing gets both.
    if is_valencia and score <= 90:
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

    llm_scored = len(scored) - title_rejected
    above_threshold = sum(1 for j in scored if j["score"] >= min_score)
    print(f"  Title filter rejected {title_rejected} jobs before LLM scoring")
    print(f"  Jobs sent to LLM: {llm_scored}")
    print(f"  Jobs above min_score ({min_score}): {above_threshold}")
    scored.sort(key=lambda j: j["score"], reverse=True)
    return scored, min_score


def main():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from fetch import fetch_new_jobs

    jobs = fetch_new_jobs()
    print(f"Scoring {len(jobs)} new jobs...")

    scored, min_score = score_jobs(jobs)
    above = [j for j in scored if j["score"] >= min_score]
    print(f"\nJobs above min_score threshold: {len(above)}\n")

    for job in above[:5]:
        print(f"[{job['score']}] {job['title']} @ {job['company']} ({job['location']})")
        print(f"  {job['reason']}")
        if job["flags"]:
            print(f"  Flags: {', '.join(job['flags'])}")
        print(f"  {job['url']}\n")


if __name__ == "__main__":
    main()
