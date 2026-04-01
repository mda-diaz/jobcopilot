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


def build_prompt(profile_str, job):
    description = (job.get("description") or "")[:2000]
    user_content = f"""USER PROFILE:
{profile_str}

JOB:
Title: {job.get("title", "")}
Company: {job.get("company", "")}
Location: {job.get("location", "")}
Description: {description}

Score this job from 0-100 based on fit with the profile.
Consider: skills match, seniority, industry, location, work mode (remote/hybrid preferred), deal-breakers.

Respond ONLY in this JSON format:
{{
  "score": <int 0-100>,
  "reason": "<exactly 2 sentences explaining the score>",
  "flags": ["<red flag 1>", "<red flag 2>"]
}}"""
    return user_content


def call_llm(profile_str, job):
    system = "You are a career advisor evaluating job fit. Respond only in valid JSON."
    user_content = build_prompt(profile_str, job)

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


def score_jobs(jobs):
    config = load_config()
    profile_str = yaml.dump(config, allow_unicode=True)
    min_score = config.get("min_score", 60)

    scored = []
    for job in jobs:
        try:
            raw = call_llm(profile_str, job)
            result = parse_response(raw)
        except Exception as e:
            print(f"[score] Error scoring '{job.get('title')}' at '{job.get('company')}': {e}")
            result = {"score": 0, "reason": "scoring error", "flags": []}

        job["score"] = int(result.get("score", 0))
        job["reason"] = result.get("reason", "")
        job["flags"] = result.get("flags", [])
        scored.append(job)

    scored.sort(key=lambda j: j["score"], reverse=True)
    return [j for j in scored if j["score"] >= min_score]


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
