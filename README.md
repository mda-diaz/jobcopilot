# jobcopilot

Automated daily job digest: scrapes LinkedIn, Indeed, and Adzuna for new listings, scores them against your profile with an LLM, tailors your CV for the top matches, and commits a markdown digest to the repo every morning.

## Setup

### 1. Clone and install

```bash
git clone <repo-url>
cd jobcopilot
pip install -r requirements.txt
```

### 2. Add your CV

> **Required — the repo does not include your CV.**

Place your CV as `config/cv.pdf`. On first run, the pipeline will extract the text and save it to `config/cv_template.md` automatically. Both files are excluded from version control via `.gitignore`.

### 3. Configure your profile

Edit `config/profile.yaml` with your name, target roles, skills, and preferences.

### 4. Set up environment variables

```bash
cp .env.example .env
```

Fill in `.env` with your API keys:

| Variable | Required | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | Recommended | Uses `claude-haiku-4-5` for scoring and tailoring |
| `OPENAI_API_KEY` | Fallback | Uses `gpt-4o-mini` if Anthropic key is absent |
| `ADZUNA_APP_ID` | Optional | Enables Adzuna job source |
| `ADZUNA_API_KEY` | Optional | Enables Adzuna job source |

At least one of `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` must be set.

### 5. Run manually

```bash
python main.py
```

Output is saved to `data/digests/`.

## Automated runs (GitHub Actions)

The workflow in `.github/workflows/daily_digest.yml` runs at **06:00 UTC** daily (07:00 Madrid in winter, 08:00 in summer).

Add the four API keys as repository secrets (Settings → Secrets and variables → Actions):
`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `ADZUNA_APP_ID`, `ADZUNA_API_KEY`

The workflow commits new digest files and the updated `seen_jobs.json` back to the repo automatically. To trigger it manually: Actions → Daily Job Digest → Run workflow.

## Project structure

```
jobcopilot/
├── main.py                  # Pipeline entry point
├── requirements.txt
├── .env.example
├── config/
│   ├── profile.yaml         # Your job search profile
│   ├── cv.pdf               # Your CV — add manually, not committed
│   └── cv_template.md       # Auto-extracted from cv.pdf, not committed
├── data/
│   ├── seen_jobs.json        # Tracks processed URLs — not committed
│   └── digests/             # Daily digest and tailored CV files
├── src/
│   ├── fetch.py             # Scrapes jobs from Indeed, LinkedIn, Adzuna
│   ├── score.py             # LLM scoring and filtering
│   ├── tailor.py            # LLM CV tailoring per job
│   └── digest.py            # Builds and saves the markdown digest
└── .github/
    └── workflows/
        └── daily_digest.yml # Scheduled GitHub Actions workflow
```
