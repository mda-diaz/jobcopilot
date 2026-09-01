import json
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent.parent
load_dotenv(BASE_DIR / ".env")

# Scoring rubric: the LLM returns one sub-score per dimension and the total is
# summed here in Python. gpt-4o-mini is unreliable at holding a weighted rubric
# in its head, and a single opaque 0-100 is impossible to debug when it is wrong.
RUBRIC_WEIGHTS = {
    "remote": 10,
    "spain_payable": 10,
    "global_company": 10,
    "human_facing": 25,
    "language": 10,
    "process_work": 10,
    "domain_bonus": 15,
}
# Weights sum to 90; the LLM's own overall judgement fills the last 10.
RUBRIC_WEIGHTS["profile_fit"] = 10


def load_config():
    with open(BASE_DIR / "config" / "profile.yaml") as f:
        return yaml.safe_load(f)


def truncate_description(text, head=1400, tail=800):
    """Keep the role summary AND the requirements block.

    Spain-eligibility and hard language requirements almost always sit at the
    very bottom of a listing, so a plain head-only truncation hid exactly the
    evidence the spain_payable and language dimensions need.
    """
    text = text or ""
    if len(text) <= head + tail:
        return text
    return text[:head] + "\n\n[...]\n\n" + text[-tail:]


def build_prompt(profile_str, work_mode_str, job):
    description = truncate_description(job.get("description"))
    user_content = f"""USER PROFILE:
{profile_str}
Preferred work mode: {work_mode_str}

HOW TO JUDGE THIS JOB:
Judge the WORK DESCRIBED, not the job title. This person's background is HR,
but the title may never say "HR", "people" or "recursos humanos" and the role
can still be an excellent match. Roles about supporting employees, partners,
vendors, clients or members in an operations capacity are frequently the same
work under a different name. Never reject on title alone.

Rate the job on each dimension below. Use the FULL range — a 5 everywhere is
a useless answer. Score only on evidence in the description; when a dimension
is genuinely not addressed, use the "silent" value named in its rule.

remote (0-10)
  Fully remote = 10. Remote with occasional travel = 8. Hybrid = 4.
  On-site in Valencia = 8 (home base, no relocation cost).
  On-site anywhere else in Spain = 1. On-site outside Spain = 0.

spain_payable (0-10)
  Can someone resident in Spain be hired and paid here? This is close to a
  deal-breaker, so be strict.
  Explicitly Spain, or EMEA/Europe-wide, or names an EOR (Deel, Remote.com,
  Oyster, Velocity, Globalization Partners) = 10.
  Remote in Europe but silent on country = 5 (the "silent" value).
  Names only other countries, or requires US/UK/other work authorization,
  or is a US-payroll role = 0.

global_company (0-10)
  Multinational, several countries, international customers or teams = 10.
  Regional with some international reach = 6.
  Single-country SME or local agency = 2.

human_facing (0-25)
  THE HEAVIEST DIMENSION — score it carefully.
  The core of the job is resolving problems FOR people through direct human
  contact: employees, partners, vendors, clients, members, candidates.
  Direct contact is the whole job = 25.
  Substantial contact alongside other duties = 15.
  Occasional stakeholder contact, mostly independent work = 6.
  Primarily coding, data analysis, design, or solo administrative work = 0.

language (0-10)
  Works in English and/or Spanish = 10.
  Another language listed as nice-to-have = 7.
  Fluent German, French, Dutch, Italian or similar as a HARD requirement = 0.

process_work (0-10)
  Structured, recurring, procedural work with clear ownership and defined
  workflows = 10. Note: HIGH REPETITION IS A POSITIVE HERE, NOT A NEGATIVE.
  This person is comfortable with repeated tasks; do not penalise them.
  Ambiguous, undefined, build-it-from-nothing work = 3.

domain_bonus (0-15)
  Sport, fitness, endurance, outdoor, athletics or wellness industry = 15.
  Adjacent — health tech, wearables, nutrition, events, sports media = 8.
  Anything else = 0. Do not award partial credit for a company that merely
  offers a gym benefit.

profile_fit (0-10)
  Everything else: skills overlap, seniority, and the deal_breakers listed in
  the profile above. A junior or intern posting scores 0 here.

ROLE TYPE RULES:
- This person works IN HR; they do not manage payroll departments or lead
  payroll teams. A Payroll Manager / Payroll Lead / Head of Payroll role gets
  profile_fit 0 and human_facing no higher than 5.
- Payroll as one skill inside a generalist or operations role is fine.
- Moving away from traditional administrative HR toward data-driven, modern or
  AI-enabled ways of working is a strong positive in profile_fit.

JOB:
Title: {job.get("title", "")}
Company: {job.get("company", "")}
Location: {job.get("location", "")}
Remote: {"yes" if job.get("remote") else "no"}
Description: {description}

Respond ONLY in this JSON format:
{{
  "scores": {{
    "remote": <int 0-10>,
    "spain_payable": <int 0-10>,
    "global_company": <int 0-10>,
    "human_facing": <int 0-25>,
    "language": <int 0-10>,
    "process_work": <int 0-10>,
    "domain_bonus": <int 0-15>,
    "profile_fit": <int 0-10>
  }},
  "reason": "<exactly 2 sentences explaining the score>",
  "non_hr_read": "<if the title is not HR-flavoured, one sentence on why the work still fits the profile — empty string if the title is clearly HR, or if it genuinely does not fit>",
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


def total_from_subscores(subscores):
    """Sum the rubric deterministically, clamping each dimension to its weight."""
    total = 0
    for key, weight in RUBRIC_WEIGHTS.items():
        try:
            value = int(subscores.get(key, 0))
        except (TypeError, ValueError):
            value = 0
        total += max(0, min(value, weight))
    return max(0, min(total, 100))


def parse_response(raw):
    try:
        # Strip markdown code fences if the model wraps its response
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        data = json.loads(text)
    except Exception:
        return {"score": 0, "reason": "parse error", "flags": [], "subscores": {}, "non_hr_read": ""}

    subscores = data.get("scores") or {}
    if not isinstance(subscores, dict):
        subscores = {}
    return {
        "score": total_from_subscores(subscores),
        "subscores": subscores,
        "reason": data.get("reason", ""),
        "non_hr_read": data.get("non_hr_read", "") or "",
        "flags": data.get("flags") or [],
    }


# ── Title gate ───────────────────────────────────────────────────────────────
# Three-way, not binary: allow / maybe / reject. The "maybe" bucket is what
# catches people-ops work hiding under a non-HR title. It is pure substring
# matching, so it costs nothing until a job actually reaches the LLM.

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
    # Operations vocabulary: the work shape this person fits, whatever the
    # profession the title claims.
    "customer success", "client services", "client success",
    "member services", "partner operations", "partner manager",
    "service delivery", "business operations", "community operations",
    "trust and safety", "trust & safety", "account coordinator",
    "program coordinator", "operations specialist", "operations coordinator",
    "atención al cliente", "soporte", "gestor de cuentas",
]

# Absolute rejects: these win over everything, including the allow list. The
# user works IN HR and does not manage payroll teams, so "payroll" appearing in
# HR_TITLE_KEYWORDS must not rescue a Payroll Manager posting.
HR_TITLE_REJECT_KEYWORDS = [
    "payroll manager", "payroll lead", "head of payroll", "payroll team manager",
]

# Profession rejects: applied ONLY when the title carries no allow-list signal.
# Checked second on purpose — a replay over 14 daily CSVs showed that treating
# these as absolute killed "Community Developer – Leadership & HR (B2B)", which
# had scored 95. A title that names both an engineering role and HR work is a
# job for the LLM to judge, not for a substring match.
PROFESSION_REJECT_KEYWORDS = [
    "software engineer", "backend", "frontend", "full stack", "fullstack",
    "developer", "desarrollador", "data engineer", "devops", "sre ",
    "machine learning engineer", "qa engineer", "security engineer",
    "nurse", "enfermer", "driver", "conductor", "chef", "cocinero",
    "warehouse", "almacén", "electrician", "electricista",
]

# Signals scanned in the description for the "maybe" bucket. Two or more, plus
# a remote tag, is enough to buy one LLM call.
MAYBE_SIGNALS = [
    "stakeholder", "escalation", "escalación", "internal teams",
    "partners", "troubleshoot", "ticket", "sla", "cross-functional",
    "spanish and english", "english and spanish", "inglés y español",
    "employee", "empleado", "point of contact", "punto de contacto",
    "resolve issues", "resolver incidencias", "case management",
]
MAYBE_MIN_SIGNALS = 2


def title_gate(job):
    """Return 'allow', 'maybe' or 'reject' for a job dict."""
    title_lower = (job.get("title") or "").lower()

    # Absolute rejects beat the allow list.
    if any(kw in title_lower for kw in HR_TITLE_REJECT_KEYWORDS):
        return "reject"
    if any(kw in title_lower for kw in HR_TITLE_KEYWORDS):
        return "allow"
    # Profession rejects only bite when nothing above matched.
    if any(kw in title_lower for kw in PROFESSION_REJECT_KEYWORDS):
        return "reject"

    # Unknown title: buy an LLM call only for remote roles whose description
    # reads like human-facing operations work.
    if not job.get("remote"):
        return "reject"
    description = (job.get("description") or "").lower()
    hits = sum(1 for s in MAYBE_SIGNALS if s in description)
    if hits >= MAYBE_MIN_SIGNALS:
        return "maybe"
    return "reject"


def is_hr_relevant(title):
    """Back-compat shim: title-only check, used by callers outside score_jobs."""
    return title_gate({"title": title}) == "allow"


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


def score_jobs(jobs, call_llm_fn=None):
    """Score jobs. Pass call_llm_fn=None-returning stub to dry-run the gate."""
    config = load_config()
    profile_str = yaml.dump(config, allow_unicode=True)
    work_mode_str = " or ".join(config.get("work_mode", ["remote", "hybrid"]))
    min_score = config.get("min_score", 60)
    llm = call_llm_fn or call_llm

    scored = []
    buckets = {"allow": 0, "maybe": 0, "reject": 0}

    for job in jobs:
        bucket = title_gate(job)
        buckets[bucket] += 1
        job["gate"] = bucket

        if bucket == "reject":
            job["score"] = 0
            job["reason"] = "Title gate: not a plausible fit"
            job["flags"] = ["irrelevant role"]
            job["subscores"] = {}
            job["non_hr_read"] = ""
            scored.append(job)
            continue

        try:
            raw = llm(profile_str, work_mode_str, job)
            result = parse_response(raw)
        except Exception as e:
            print(f"[score] Error scoring '{job.get('title')}' at '{job.get('company')}': {e}")
            result = {"score": 0, "reason": "scoring error", "flags": [], "subscores": {}, "non_hr_read": ""}

        score, flags = apply_penalties(job, int(result.get("score", 0)), result.get("flags", []))
        job["score"] = score
        job["reason"] = result.get("reason", "")
        job["subscores"] = result.get("subscores", {})
        job["non_hr_read"] = result.get("non_hr_read", "")
        job["flags"] = flags
        scored.append(job)

    llm_scored = buckets["allow"] + buckets["maybe"]
    above_threshold = sum(1 for j in scored if j["score"] >= min_score)
    print(f"  Title gate: {buckets['allow']} allow, {buckets['maybe']} maybe, {buckets['reject']} reject")
    print(f"  Jobs sent to LLM: {llm_scored}")
    print(f"  Jobs above min_score ({min_score}): {above_threshold}")
    scored.sort(key=lambda j: j["score"], reverse=True)
    return scored, min_score


def main():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from fetch import fetch_new_jobs

    dry_run = "--no-llm" in sys.argv

    jobs = fetch_new_jobs()
    print(f"Scoring {len(jobs)} new jobs...")

    if dry_run:
        print("  (--no-llm: gate only, no API calls)")
        stub = lambda *a, **k: '{"scores": {}, "reason": "dry run", "flags": []}'
        scored, min_score = score_jobs(jobs, call_llm_fn=stub)
        for job in scored:
            if job.get("gate") == "maybe":
                print(f"  [maybe] {job.get('title')} @ {job.get('company')}")
        return

    scored, min_score = score_jobs(jobs)
    above = [j for j in scored if j["score"] >= min_score]
    print(f"\nJobs above min_score threshold: {len(above)}\n")

    for job in above[:5]:
        print(f"[{job['score']}] {job['title']} @ {job['company']} ({job['location']})")
        print(f"  {job['reason']}")
        if job.get("non_hr_read"):
            print(f"  Non-HR read: {job['non_hr_read']}")
        if job.get("subscores"):
            print(f"  Sub-scores: {job['subscores']}")
        if job["flags"]:
            print(f"  Flags: {', '.join(job['flags'])}")
        print(f"  {job['url']}\n")


if __name__ == "__main__":
    main()
