# jobcopilot

A daily job search copilot. Run it in the morning, get a ranked list of HR jobs with a tailored CV for each top role — so you know exactly what to apply to today.

---

## The problem

Job searching isn't hard because there aren't enough jobs. It's hard because there's too much noise. You spend 40 minutes scrolling, apply to three things that seemed okay, and spend the next week wondering if any of them were actually worth it.

What eats your time isn't applying — it's the daily triage: scanning listings, judging fit, rewriting your CV summary for each role. This tool does that part for you.

---

## What it does

Runs a pipeline that:

1. Fetches jobs from the last 24–72 hours across Indeed, LinkedIn, and Adzuna
2. Scores each job 0–100 against your profile — skills, seniority, work mode, deal-breakers
3. Filters to the top 5 and skips anything you've already seen
4. Rewrites your CV summary and key bullets for the top 3 roles
5. Saves two files: a markdown digest with reasoning and apply links, and a CSV with all scored jobs

You open one file and already know what to do.

It does **not** auto-apply. That's deliberate — mass applications hurt more than they help.

---

## Job sources

| Source | Status |
|--------|--------|
| Indeed | ✅ Active |
| LinkedIn | ✅ Active | 
| Adzuna | ✅ Active |

---

## Setup

Requires Python 3.10+.

```bash
git clone https://github.com/mda-diaz/jobcopilot.git
cd jobcopilot
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Place your CV at `config/cv.pdf` — it gets extracted automatically on first run.

Edit `config/profile.yaml` with your search terms, skills, location, and deal-breakers.

Copy `.env.example` to `.env` and fill in your keys:

```
ANTHROPIC_API_KEY=your_key_here        # console.anthropic.com
OPENAI_API_KEY=your_key_here           # optional fallback
ADZUNA_APP_ID=your_id_here             # free at developer.adzuna.com
ADZUNA_API_KEY=your_key_here
```

Only `ANTHROPIC_API_KEY` is required to run.

---

## Run

```bash
source venv/bin/activate
python3 main.py
```

---

## Output

Two files land in `data/digests/` after each run:

**`digest_YYYY-MM-DD.md`** — top 5 jobs with score, reasoning, red flags, apply link, and path to tailored CV

**`jobs_YYYY-MM-DD.csv`** — all scored jobs ranked by fit, openable in Excel or Google Sheets

---

## Cost

Uses Claude Haiku by default (GPT-4o-mini as fallback). Roughly **€0.03–0.06 per run** — under €1.50/month running daily.

---

## Project structure

```
jobcopilot/
├── .github/workflows/daily_digest.yml   # optional: runs automatically at 07:00
├── config/
│   ├── profile.yaml                     # your search preferences
│   └── cv.pdf                           # your CV (not committed to git)
├── data/
│   ├── seen_jobs.json                   # dedup cache
│   └── digests/                         # daily output
├── src/
│   ├── fetch.py                         # job scraping
│   ├── score.py                         # LLM scoring
│   ├── tailor.py                        # CV rewriting
│   └── digest.py                        # output generation
├── main.py
├── requirements.txt
└── .env.example
```

---

## Automatic daily run (optional)

Push to GitHub, add your API keys as repository secrets (Settings → Secrets → Actions), and the workflow runs automatically at 07:00 Madrid time. Results are committed back to the repo in `data/digests/`.
