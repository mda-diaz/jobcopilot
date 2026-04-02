import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

# Add src/ to path so modules are importable without a package install
sys.path.insert(0, str(BASE_DIR / "src"))

import digest
import fetch
import score
import tailor

SEEN_JOBS_PATH = BASE_DIR / "data" / "seen_jobs.json"


def load_seen_jobs():
    with open(SEEN_JOBS_PATH) as f:
        return json.load(f)


def save_seen_jobs(existing, new_jobs):
    seen_urls = {job["url"] for job in existing if job.get("url")}
    to_append = [{"url": job["url"]} for job in new_jobs if job.get("url") and job["url"] not in seen_urls]
    updated = existing + to_append
    with open(SEEN_JOBS_PATH, "w") as f:
        json.dump(updated, f, indent=2)
    return len(to_append)


def main():
    start = time.time()

    # ── Step 1: Fetch ────────────────────────────────────────────────────────
    print("Fetching jobs...")
    try:
        jobs = fetch.fetch_new_jobs()
        print(f"Found {len(jobs)} new jobs")
    except Exception as e:
        print(f"[ERROR] Fetch step failed: {e}")
        return

    if not jobs:
        print("No new jobs to process. Exiting.")
        return

    # ── Step 2: Score ────────────────────────────────────────────────────────
    print("\nScoring jobs...")
    try:
        scored, min_score = score.score_jobs(jobs)
        above = [j for j in scored if j["score"] >= min_score]
        print(f"{len(scored)} jobs scored, {len(above)} above minimum score ({min_score})")
    except Exception as e:
        print(f"[ERROR] Scoring step failed: {e}")
        return

    # ── Step 3: Tailor CVs for top 3 ────────────────────────────────────────
    top_jobs = above[:5]
    print("\nTailoring CVs for top 3 jobs...")
    cv_paths = []
    for job in top_jobs[:3]:
        try:
            path = tailor.tailor_cv(job)
            cv_paths.append(path)
        except Exception as e:
            print(f"[ERROR] Tailor failed for '{job.get('title')}' @ '{job.get('company')}': {e}")
            cv_paths.append(None)

    # ── Step 4: Build digest ─────────────────────────────────────────────────
    print("\nBuilding digest...")
    try:
        digest_path, csv_path = digest.create_digest(
            top_jobs, cv_paths, total_jobs_fetched=len(jobs), all_scored_jobs=scored  # scored = ALL jobs
        )
        print(f"Digest saved to {digest_path}")
        print(f"CSV saved to {csv_path}")
    except Exception as e:
        print(f"[ERROR] Digest step failed: {e}")

    # ── Step 5: Update seen_jobs.json ────────────────────────────────────────
    try:
        existing = load_seen_jobs()
        added = save_seen_jobs(existing, jobs)
        print(f"\nMarked {added} new job URL(s) as seen.")
    except Exception as e:
        print(f"[ERROR] Failed to update seen_jobs.json: {e}")

    elapsed = time.time() - start
    print(f"\nDone in {elapsed:.1f}s")


if __name__ == "__main__":
    main()
