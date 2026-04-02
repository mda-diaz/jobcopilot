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


def _parse_jobspy_df(df, site):
    """Convert a jobspy DataFrame to a list of job dicts."""
    jobs = []
    for _, row in df.iterrows():
        url = row.get("job_url") or row.get("url") or ""
        if not url:
            continue
        date_posted = row.get("date_posted")
        if isinstance(date_posted, datetime):
            date_posted = date_posted.date().isoformat()
        elif date_posted is not None:
            date_posted = str(date_posted)
        jobs.append({
            "title": str(row.get("title") or ""),
            "company": str(row.get("company") or ""),
            "location": str(row.get("location") or ""),
            "description": str(row.get("description") or ""),
            "url": url,
            "source": str(row.get("site") or site),
            "date_posted": date_posted,
        })
    return jobs


def fetch_jobspy(search_terms, location="Spain"):
    # infojobs is not supported by jobspy; it can be added later via the Adzuna API
    sites = ["indeed", "linkedin"]
    results = []

    for term in search_terms:
        for site in sites:
            try:
                df = scrape_jobs(
                    site_name=[site],
                    search_term=term,
                    location=location,
                    results_wanted=50,
                    hours_old=24,
                    linkedin_fetch_description=True,
                )
                count = len(df) if df is not None else 0
                if count == 0:
                    print(f"  [jobspy:{site}] 0 results for '{term}' — site may be blocking scraping")
                    continue
                print(f"  [jobspy:{site}] {count} results for '{term}'")
                results.extend(_parse_jobspy_df(df, site))
            except Exception as e:
                print(f"  [jobspy:{site}] Error fetching '{term}': {e}")

    return results


def fetch_jobspy_remote(search_terms):
    """Second pass: LinkedIn-only, Europe-wide, remote filter."""
    results = []

    for term in search_terms:
        try:
            df = scrape_jobs(
                site_name=["linkedin"],
                search_term=term,
                location="Europe",
                results_wanted=50,
                hours_old=24,
                is_remote=True,
                linkedin_fetch_description=True,
            )
            count = len(df) if df is not None else 0
            if count == 0:
                print(f"  [jobspy:linkedin:remote] 0 results for '{term}'")
                continue
            print(f"  [jobspy:linkedin:remote] {count} results for '{term}'")
            results.extend(_parse_jobspy_df(df, "linkedin"))
        except Exception as e:
            print(f"  [jobspy:linkedin:remote] Error fetching '{term}': {e}")

    return results


def fetch_adzuna(search_terms, location="Spain", country="es"):
    app_id = os.getenv("ADZUNA_APP_ID")
    app_key = os.getenv("ADZUNA_API_KEY")
    if not app_id or not app_key:
        print("  [adzuna] Skipping — ADZUNA_APP_ID or ADZUNA_API_KEY not set in .env")
        return []

    results = []
    for term in search_terms:
        try:
            response = requests.get(
                f"https://api.adzuna.com/v1/api/jobs/{country}/search/1",
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
            jobs = response.json().get("results", [])
            print(f"  [adzuna] {len(jobs)} results for '{term}'")
            for job in jobs:
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
            print(f"  [adzuna] Error fetching '{term}': {e}")
    return results


def deduplicate(jobs):
    seen = set()
    unique = []
    for job in jobs:
        if job["url"] not in seen:
            seen.add(job["url"])
            unique.append(job)
    return unique


def tag_remote(jobs, remote_urls):
    """Add a 'remote' boolean field to each job."""
    remote_keywords = ["remote", "remoto", "teletrabajo", "telework"]
    for job in jobs:
        in_remote_search = job["url"] in remote_urls
        text = (job.get("title", "") + " " + job.get("description", "")).lower()
        has_keyword = any(kw in text for kw in remote_keywords)
        job["remote"] = in_remote_search or has_keyword
    return jobs


SPAIN_LOCATIONS = [
    "spain", "españa", "madrid", "barcelona", "valencia", "sevilla",
    "bilbao", "málaga", "malaga", "zaragoza",
]

REMOTE_KEYWORDS = [
    "remote", "remoto", "trabajo remoto", "full remote",
    "remote europe", "remote emea", "work from anywhere",
]


def filter_location(jobs):
    filtered = []
    removed = 0
    for job in jobs:
        location = (job.get("location") or "").lower()
        text = (job.get("title", "") + " " + job.get("description", "")).lower()

        is_spain = any(s in location for s in SPAIN_LOCATIONS)
        is_remote = any(kw in text for kw in REMOTE_KEYWORDS)
        no_location = not location.strip()

        if is_spain or is_remote or no_location:
            filtered.append(job)
        else:
            removed += 1

    print(f"  Location filter removed {removed} jobs, {len(filtered)} remaining")
    return filtered


def fetch_new_jobs():
    config = load_config()
    search_terms = config.get("search_terms", [])
    location = config.get("location", "Spain")
    country = config.get("country", "es")

    print("Scraping Spain-based listings...")
    jobspy_results = fetch_jobspy(search_terms, location)

    print("Scraping Europe-wide remote listings...")
    remote_results = fetch_jobspy_remote(search_terms)
    remote_urls = {j["url"] for j in remote_results}

    print("Fetching from Adzuna...")
    adzuna_results = fetch_adzuna(search_terms, location, country)

    indeed_count = sum(1 for j in jobspy_results if j.get("source") == "indeed")
    linkedin_count = sum(1 for j in jobspy_results if j.get("source") == "linkedin")
    print(f"  Total — LinkedIn: {linkedin_count}, Indeed: {indeed_count}, "
          f"LinkedIn remote: {len(remote_results)}, Adzuna: {len(adzuna_results)}")

    all_jobs = deduplicate(jobspy_results + remote_results + adzuna_results)
    all_jobs = filter_location(all_jobs)
    all_jobs = tag_remote(all_jobs, remote_urls)

    seen_urls = load_seen_urls()
    new_jobs = [job for job in all_jobs if job["url"] not in seen_urls]

    return new_jobs


def main():
    new_jobs = fetch_new_jobs()
    print(f"New jobs found: {len(new_jobs)}")
    remote_count = sum(1 for j in new_jobs if j.get("remote"))
    print(f"  of which remote/hybrid: {remote_count}")


if __name__ == "__main__":
    main()
