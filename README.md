# AI Job Hunter

A daily job search copilot that finds relevant jobs, scores them against your profile, tailors your CV, and delivers a digest every morning — so you know exactly what to apply to today.

---

## The problem

Job searching is exhausting not because there aren't enough jobs, but because there's too much noise. You open LinkedIn, scroll for 40 minutes, apply to three things that seemed okay, and spend the next week wondering if any of them were actually a good fit.

The existing "AI job tools" don't really fix this. Most of them automate the wrong part — they'll blast your CV to 200 jobs automatically, which gets you ignored faster. The signal problem stays unsolved.

What actually eats your time isn't applying. It's the daily triage: scanning listings, judging fit, rewriting your summary for each role, and deciding which three things are worth your afternoon.

---

## What this solves

Every morning at 07:00, this tool runs a pipeline that:

1. Scrapes the last 24 hours of job postings across InfoJobs, Indeed, and Adzuna for your saved search terms
2. Scores each job 0–100 against your profile using an LLM — skills match, seniority, location, compensation signals
3. Filters to the top 3–5 and discards anything you've already seen
4. Rewrites the relevant sections of your CV to match each of the top roles
5. Saves a digest file with the ranked jobs, the reasoning behind each score, tailored CVs, and direct application links

You wake up, open one file, and you already know what to do.

---

## What it does NOT do

It does not auto-apply on your behalf. That's a deliberate choice — automated mass applications hurt more than they help, and you lose any sense of which applications are worth following up on.

The goal is to make the decision and preparation part take 10 minutes instead of an hour, then let you apply as a human.

---

## How it works

```
Cron (07:00) → Fetch jobs → Score + rank → Filter top 5 → Tailor CVs → Save digest
```

Each step is a separate Python module, so you can run them individually or swap out any piece (different job source, different LLM, different output format).

**Stack:** Python, python-jobspy, Claude Haiku / GPT-4o-mini (cheapest option per call), GitHub Actions for scheduling, plain JSON for state.

**Cost:** roughly €0.10–0.35/day in LLM API calls depending on how many jobs get scored.

---

## Setup

### 1. Clone and install

```bash
git clone https://github.com/your-username/ai-job-hunter.git
cd ai-job-hunter
pip install -r requirements.txt
```

### 2. Configure your profile

Edit `config/profile.yaml` with your job titles, location, skills, and search terms. This is what the LLM scores jobs against — the more specific, the better.

```yaml
name: Your Name
location: Madrid, Spain
language: es
search_terms:
  - "product manager"
  - "jefe de producto"
seniority: senior
skills:
  - product strategy
  - stakeholder management
  - SQL
  - agile
deal_breakers:
  - "requires 10+ years"
  - junior
```

### 3. Add your CV

Place your CV as `config/cv.pdf`. The pipeline extracts and stores it as `config/cv_template.md` on first run.

### 4. Set environment variables

Copy `.env.example` to `.env` and fill in your API keys:

```bash
cp .env.example .env
```

```
ANTHROPIC_API_KEY=your_key_here
OPENAI_API_KEY=your_key_here       # optional, used as fallback
ADZUNA_APP_ID=your_id_here
ADZUNA_API_KEY=your_key_here
```

### 5. Run manually

```bash
python main.py
```

Output lands in `data/digests/digest_YYYY-MM-DD.md`.

### 6. Schedule it (GitHub Actions)

Push to GitHub and add your API keys as repository secrets. The workflow in `.github/workflows/daily_digest.yml` runs automatically at 07:00 Madrid time.

---

## Output format

Each daily digest looks like this:

```
# Job Digest — 2025-01-15

## 1. Senior Product Manager — Cabify (Score: 87/100)
**Why:** Strong match on marketplace experience and Spanish market focus.
         Your background in growth and ops aligns directly with the role scope.
**Red flags:** None
**Apply:** https://...

[Tailored CV — cv_cabify_2025-01-15.md]

---

## 2. ...
```

---

## Project structure

```
ai-job-hunter/
├── .github/workflows/daily_digest.yml
├── config/
│   ├── profile.yaml
│   └── cv_template.md
├── data/
│   ├── seen_jobs.json
│   └── digests/
├── src/
│   ├── fetch.py
│   ├── score.py
│   ├── tailor.py
│   └── digest.py
├── main.py
├── requirements.txt
├── .env.example
└── README.md
```

---

## Extending it

Adding a new job source means adding one entry to the `site_name` list in `fetch.py`. The scoring and CV tailoring steps don't care where jobs came from.

Planned next steps (not in MVP):
- Email delivery via Resend instead of file output
- Simple web UI to review and mark jobs as applied
- Feedback loop: jobs you apply to improve the scoring model over time
