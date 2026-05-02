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
    # Google Jobs aggregates InfoJobs and other Spanish boards, covering them without a separate API
    sites = ["indeed", "linkedin", "glassdoor", "google"]
    results = []

    for term in search_terms:
        for site in sites:
            try:
                kwargs = dict(
                    site_name=[site],
                    search_term=term,
                    location=location,
                    results_wanted=50,
                    hours_old=24,
                    linkedin_fetch_description=True,
                    country_indeed="spain",
                )
                if site == "google":
                    kwargs["google_search_term"] = (
                        f"{term} Spain site:infojobs.net OR site:linkedin.com OR site:indeed.com"
                    )

                df = scrape_jobs(**kwargs)
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


BLOCKED_DOMAINS = [
    "trabajo.org",
    "es.trabajo.org",
]


def filter_blocked_sources(jobs):
    filtered = []
    removed = 0
    for job in jobs:
        url = job.get("url") or ""
        if any(blocked in url for blocked in BLOCKED_DOMAINS):
            removed += 1
        else:
            filtered.append(job)
    print(f"  Blocked {removed} jobs from low quality sources")
    return filtered


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
    for job in jobs:
        in_remote_search = job["url"] in remote_urls
        text = (job.get("title", "") + " " + job.get("description", "")).lower()
        has_keyword = any(s in text for s in REMOTE_TAG_SIGNALS)
        job["remote"] = in_remote_search or has_keyword
    return jobs


REMOTE_SIGNALS = [
    "remote europe", "remote emea", "work from anywhere",
    "fully remote", "100% remote", "teletrabajo",
    "trabajo remoto", "remoto", "desde casa",
    "remote-first", "distributed team",
]

REMOTE_TAG_SIGNALS = REMOTE_SIGNALS + ["remote", "full remote"]

# Strict whitelist — a job must match at least one of these in its location field.
# Only remote signals are checked against the full text (title + description).
SPAIN_WHITELIST = [
    # Country
    "spain", "españa", "espana",
    # Comunidad Valenciana
    "valencia", "valenciana", "castellon", "castellón",
    "alicante", "comunidad valenciana",
    # Major cities / provinces
    "madrid", "barcelona", "sevilla", "seville", "bilbao",
    "málaga", "malaga", "zaragoza", "murcia", "palma",
    "las palmas", "pamplona", "santander", "valladolid",
    "vigo", "gijon", "gijón", "granada", "salamanca",
    "burgos", "albacete", "córdoba", "cordoba", "tarragona",
    "lleida", "girona", "cadiz", "cádiz", "huelva", "badajoz",
    "toledo", "cuenca", "logroño", "lograno", "vitoria",
    "donostia", "san sebastian", "oviedo", "leon", "león",
    "lugo", "ourense", "pontevedra", "elche", "marbella",
    "jerez", "sabadell", "terrassa", "badalona", "getafe",
    "fuenlabrada", "leganés", "leganes", "alcalá de henares",
    "alcala de henares", "almería", "almeria", "cartagena",
    # Regions / autonomías
    "cantabria", "asturias", "galicia", "cataluña", "catalonia",
    "país vasco", "pais vasco", "euskadi", "andalucía", "andalucia",
    "comunidad de madrid", "navarra", "aragón", "aragon",
    "extremadura", "castilla", "canarias", "canary islands",
    "baleares", "balearic islands", "la rioja",
    # Country-code patterns used by jobspy (e.g. "Paterna, VC, ES")
    ", es", "es,",
    # Valencia metro area
    "paterna", "sagunto", "torrent", "burjassot", "mislata", "aldaia",
    "manises", "quart de poblet", "xirivella", "catarroja",
    "paiporta", "picanya", "bétera", "betera", "gandia", "ontinyent",
    "alzira", "sueca", "xàtiva", "xativa", "requena",
    # Remote signals that explicitly open to Spain
    "remote spain", "spain remote", "remoto españa",
    "teletrabajo españa", "remote emea", "remote europe",
    "work from anywhere", "fully remote", "100% remote",
    "teletrabajo", "trabajo remoto", "remoto",
]


def is_location_valid(job):
    """Return (valid: bool, reason: str).

    Whitelist-only: a job passes only if its location field contains a
    Spain/Spanish-city term, OR if its location is empty/remote AND its
    description contains a genuine remote-work signal.
    """
    location = (job.get("location") or "").lower().strip()
    desc = (job.get("description") or "")[:2000].lower()
    combined = location + " " + desc

    # Location explicitly matches whitelist → pass
    if any(term in location for term in SPAIN_WHITELIST):
        return True, "spain"

    # Location is empty or generic "remote" → only pass if description
    # contains a genuine remote-work signal (teletrabajo, fully remote, etc.)
    if not location or location in ("remote", "none", "unknown", "anywhere"):
        has_remote = any(s in combined for s in REMOTE_SIGNALS)
        if has_remote:
            return True, "remote"
        return False, "no_location_no_remote"

    # Location present but not on whitelist → reject
    return False, "non_spain"


def filter_location(jobs):
    counts = {
        "passed_spain": 0,
        "passed_remote": 0,
        "rejected_non_spain": 0,
        "rejected_no_location": 0,
    }
    rejected_examples = []
    filtered = []

    for job in jobs:
        valid, reason = is_location_valid(job)
        if valid:
            if reason == "spain":
                counts["passed_spain"] += 1
            else:
                counts["passed_remote"] += 1
            filtered.append(job)
        else:
            if reason == "non_spain":
                counts["rejected_non_spain"] += 1
                label = "non-Spain location"
            else:
                counts["rejected_no_location"] += 1
                label = "no location + no remote signal"
            if len(rejected_examples) < 5:
                rejected_examples.append(
                    (job.get("title", ""), job.get("company", ""), job.get("location", ""), label)
                )

    total_rejected = counts["rejected_non_spain"] + counts["rejected_no_location"]
    print("  Location filter results (whitelist-only):")
    print(f"    Passed (Spain location):        {counts['passed_spain']}")
    print(f"    Passed (remote signal in desc): {counts['passed_remote']}")
    print(f"    Rejected (non-Spain location):  {counts['rejected_non_spain']}")
    print(f"    Rejected (no location/remote):  {counts['rejected_no_location']}")
    print(f"    Total rejected:                 {total_rejected}")
    if rejected_examples:
        print("  Sample rejected:")
        for title, company, loc, label in rejected_examples:
            print(f"    [{label}] \"{title}\" @ {company} — {loc}")
    return filtered


NON_EN_ES_INDICATORS = [
    # German
    "deutsch", "deutschkenntnisse", "deutschsprachig", "kenntnisse",
    "stellenangebot", "bewerbung", "berufserfahrung", "vollzeit",
    "teilzeit", "arbeitgeber", "sprachkenntnisse", "c2 deutsch",
    "muttersprache deutsch", "fließend deutsch",
    # French
    "connaissance", "expérience", "entreprise", "poste", "candidature",
    "compétences", "rejoindre", "rémunération", "diplôme",
    # Italian
    "esperienza", "azienda", "ricerca", "candidato", "offerta di lavoro",
    "contratto", "laurea", "stipendio", "assunzione",
]


def is_english_or_spanish(text):
    """Returns True if text appears to be in English or Spanish."""
    text_lower = text.lower()
    return not any(indicator in text_lower for indicator in NON_EN_ES_INDICATORS)


def filter_language(jobs):
    filtered = []
    removed = 0
    for job in jobs:
        text = job.get("title", "") + " " + job.get("description", "")
        if is_english_or_spanish(text):
            filtered.append(job)
        else:
            removed += 1
    print(f"  Language filter removed {removed} jobs, {len(filtered)} remaining")
    return filtered


UNSUPPORTED_LANGUAGES = [
    "russian", "ruso", "fluent in russian",
    "german", "alemán", "deutsch", "fluent in german",
    "french", "francés", "français", "fluent in french",
    "italian", "italiano", "fluent in italian",
    "native portuguese", "fluent portuguese required",
    "dutch", "holandés", "fluent in dutch",
    "mandarin", "chinese", "cantonese",
]

REQUIREMENT_SIGNALS = [
    "required", "must", "fluent", "native", "proficiency required",
    "mandatory", "essential", "obligatorio", "imprescindible", "requerido",
]

NICE_TO_HAVE_SIGNALS = [
    "a plus", "nice to have", "bonus", "preferred",
    "valorable", "se valorará", "deseable",
]


def has_unsupported_language_requirement(text):
    """Returns True if the job requires a language other than English or Spanish."""
    text_lower = text.lower()
    nice_to_have = any(phrase in text_lower for phrase in NICE_TO_HAVE_SIGNALS)
    if nice_to_have:
        return False
    for lang in UNSUPPORTED_LANGUAGES:
        if lang in text_lower:
            if any(signal in text_lower for signal in REQUIREMENT_SIGNALS):
                return True
    return False


def filter_language_requirements(jobs):
    filtered = []
    removed = 0
    for job in jobs:
        text = job.get("title", "") + " " + job.get("description", "")
        if has_unsupported_language_requirement(text):
            removed += 1
        else:
            filtered.append(job)
    print(f"  Language requirement filter removed {removed} jobs, {len(filtered)} remaining")
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

    def _count(jobs, source):
        return sum(1 for j in jobs if j.get("source") == source)

    print(
        f"  Raw counts — LinkedIn: {_count(jobspy_results, 'linkedin')}, "
        f"Indeed: {_count(jobspy_results, 'indeed')}, "
        f"Glassdoor: {_count(jobspy_results, 'glassdoor')}, "
        f"Google: {_count(jobspy_results, 'google')}, "
        f"LinkedIn remote: {len(remote_results)}, "
        f"Adzuna: {len(adzuna_results)}"
    )

    raw_total = len(jobspy_results) + len(remote_results) + len(adzuna_results)
    print(f"  Total raw (before dedup): {raw_total}")
    all_jobs = deduplicate(jobspy_results + remote_results + adzuna_results)
    print(f"  After dedup: {len(all_jobs)} jobs")

    print("Applying domain blocklist...")
    all_jobs = filter_blocked_sources(all_jobs)
    print(f"  After domain blocklist: {len(all_jobs)} jobs")

    print("Applying location filter...")
    all_jobs = filter_location(all_jobs)
    print(f"  After location filter: {len(all_jobs)} jobs")

    print("Applying language filter...")
    all_jobs = filter_language(all_jobs)
    print(f"  After language filter: {len(all_jobs)} jobs")

    print("Applying language requirements filter...")
    all_jobs = filter_language_requirements(all_jobs)
    print(f"  After language requirements filter: {len(all_jobs)} jobs")

    all_jobs = tag_remote(all_jobs, remote_urls)

    seen_urls = load_seen_urls()
    new_jobs = [job for job in all_jobs if job["url"] not in seen_urls]

    sources = {}
    for j in new_jobs:
        src = j.get("source", "unknown")
        sources[src] = sources.get(src, 0) + 1
    print("  Post-filter source breakdown:")
    for src, count in sorted(sources.items(), key=lambda x: -x[1]):
        print(f"    {src}: {count}")

    return new_jobs


def main():
    new_jobs = fetch_new_jobs()
    print(f"New jobs found: {len(new_jobs)}")
    remote_count = sum(1 for j in new_jobs if j.get("remote"))
    print(f"  of which remote/hybrid: {remote_count}")


if __name__ == "__main__":
    main()
