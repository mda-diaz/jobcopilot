import json
import os
from datetime import datetime
from pathlib import Path

import requests
import yaml
from dotenv import load_dotenv
from jobspy import scrape_jobs

BASE_DIR = Path(__file__).parent.parent
load_dotenv(BASE_DIR / ".env")


def load_config():
    with open(BASE_DIR / "config" / "profile.yaml") as f:
        return yaml.safe_load(f)


def load_seen_urls():
    seen_path = BASE_DIR / "data" / "seen_jobs.json"
    with open(seen_path) as f:
        seen = json.load(f)
    return {job["url"] for job in seen if job.get("url")}


def fetch_jobspy(search_terms, location="Spain"):
    results = []
    for term in search_terms:
        try:
            df = scrape_jobs(
                # infojobs is not supported by jobspy; it can be added later via the Adzuna API
                site_name=["indeed", "linkedin"],
                search_term=term,
                location=location,
                results_wanted=50,
                hours_old=24,
            )
            for _, row in df.iterrows():
                url = row.get("job_url") or row.get("url") or ""
                if not url:
                    continue
                date_posted = row.get("date_posted")
                if isinstance(date_posted, datetime):
                    date_posted = date_posted.date().isoformat()
                elif date_posted is not None:
                    date_posted = str(date_posted)
                results.append({
                    "title": str(row.get("title") or ""),
                    "company": str(row.get("company") or ""),
                    "location": str(row.get("location") or ""),
                    "description": str(row.get("description") or ""),
                    "url": url,
                    "source": str(row.get("site") or "jobspy"),
                    "date_posted": date_posted,
                })
        except Exception as e:
            print(f"[jobspy] Error fetching '{term}': {e}")
    return results


def fetch_adzuna(search_terms, location="Spain"):
    app_id = os.getenv("ADZUNA_APP_ID")
    app_key = os.getenv("ADZUNA_API_KEY")
    if not app_id or not app_key:
        return []

    results = []
    for term in search_terms:
        try:
            response = requests.get(
                "https://api.adzuna.com/v1/api/jobs/es/search/1",
                params={
                    "app_id": app_id,
                    "app_key": app_key,
                    "what": term,
                    "where": location,
                    "max_days_old": 1,
                    "results_per_page": 50,
                },
                timeout=10,
            )
            response.raise_for_status()
            for job in response.json().get("results", []):
                url = job.get("redirect_url") or ""
                if not url:
                    continue
                created = job.get("created", "")
                date_posted = created[:10] if created else None
                results.append({
                    "title": job.get("title", ""),
                    "company": job.get("company", {}).get("display_name", ""),
                    "location": job.get("location", {}).get("display_name", ""),
                    "description": job.get("description", ""),
                    "url": url,
                    "source": "adzuna",
                    "date_posted": date_posted,
                })
        except Exception as e:
            print(f"[adzuna] Error fetching '{term}': {e}")
    return results


def deduplicate(jobs):
    seen = set()
    unique = []
    for job in jobs:
        if job["url"] not in seen:
            seen.add(job["url"])
            unique.append(job)
    return unique


def fetch_new_jobs():
    config = load_config()
    search_terms = config.get("search_terms", [])
    location = config.get("location", "Spain")

    jobspy_results = fetch_jobspy(search_terms, location)
    adzuna_results = fetch_adzuna(search_terms, location)

    indeed_count = sum(1 for j in jobspy_results if j.get("source") == "indeed")
    linkedin_count = sum(1 for j in jobspy_results if j.get("source") == "linkedin")
    print(f"  LinkedIn: {linkedin_count} jobs, Indeed: {indeed_count} jobs, Adzuna: {len(adzuna_results)} jobs")

    all_jobs = deduplicate(jobspy_results + adzuna_results)

    seen_urls = load_seen_urls()
    new_jobs = [job for job in all_jobs if job["url"] not in seen_urls]

    return new_jobs


def main():
    new_jobs = fetch_new_jobs()
    print(f"New jobs found: {len(new_jobs)}")


if __name__ == "__main__":
    main()
