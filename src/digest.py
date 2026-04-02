import csv
from datetime import date, datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
DIGESTS_DIR = BASE_DIR / "data" / "digests"


def build_digest(jobs, cv_paths, total_jobs_fetched=None):
    """
    jobs      — scored+sorted list of job dicts
    cv_paths  — list of cv file paths aligned with jobs (top 3 only); use None for missing entries
    total_jobs_fetched — total number of jobs analysed before filtering (optional)
    """
    today = date.today().isoformat()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    total = total_jobs_fetched if total_jobs_fetched is not None else len(jobs)

    lines = [f"# Job Digest — {today}", ""]

    for rank, job in enumerate(jobs, start=1):
        cv_path = cv_paths[rank - 1] if rank - 1 < len(cv_paths) else None

        flags = job.get("flags") or []
        flags_str = ", ".join(flags) if flags else "Ninguna"
        cv_str = cv_path if cv_path else "N/A"

        lines += [
            f"## {rank}. {job.get('title', '')} — {job.get('company', '')} (Score: {job.get('score', 0)}/100)",
            f"**Por qué:** {job.get('reason', '')}",
            f"**Alertas:** {flags_str}",
            f"**Aplicar:** {job.get('url', '')}",
            f"**CV adaptado:** {cv_str}",
            "",
            "---",
            "",
        ]

    lines.append(f"*Generado el {now}. {total} ofertas analizadas hoy.*")

    return "\n".join(lines)


def save_digest(content):
    DIGESTS_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    output_path = DIGESTS_DIR / f"digest_{today}.md"
    output_path.write_text(content, encoding="utf-8")
    return str(output_path)


def save_csv(all_scored_jobs):
    DIGESTS_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    output_path = DIGESTS_DIR / f"jobs_{today}.csv"
    fields = ["rank", "title", "company", "location", "remote", "score", "reason", "flags", "url", "source", "date_posted"]
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for rank, job in enumerate(all_scored_jobs, start=1):
            writer.writerow({
                "rank": rank,
                "title": job.get("title", ""),
                "company": job.get("company", ""),
                "location": job.get("location", ""),
                "remote": "yes" if job.get("remote") else "no",
                "score": job.get("score", 0),
                "reason": job.get("reason", ""),
                "flags": " | ".join(job.get("flags") or []),
                "url": job.get("url", ""),
                "source": job.get("source", ""),
                "date_posted": job.get("date_posted", ""),
            })
    return str(output_path)


def create_digest(jobs, cv_paths, total_jobs_fetched=None, all_scored_jobs=None):
    content = build_digest(jobs, cv_paths, total_jobs_fetched)
    path = save_digest(content)
    print(f"[digest] Saved digest to {path}")
    csv_path = save_csv(all_scored_jobs if all_scored_jobs is not None else jobs)
    print(f"[digest] Saved CSV to {csv_path}")
    return path, csv_path


def main():
    dummy_jobs = [
        {
            "title": "Senior Product Manager",
            "company": "Acme Fintech",
            "location": "Madrid, Spain",
            "url": "https://example.com/job/1",
            "score": 88,
            "reason": "Strong match on fintech and roadmap experience. SQL and analytics skills align well.",
            "flags": [],
        },
        {
            "title": "Director de Producto",
            "company": "StartupXYZ",
            "location": "Barcelona, Spain (remote)",
            "url": "https://example.com/job/2",
            "score": 74,
            "reason": "Good industry fit and seniority level. Location is outside Madrid but role is remote.",
            "flags": ["Ubicación fuera de Madrid"],
        },
        {
            "title": "Product Manager",
            "company": "Ecommerce Co",
            "location": "Remote",
            "url": "https://example.com/job/3",
            "score": 61,
            "reason": "Partial skills match with ecommerce background. Missing agile leadership signals.",
            "flags": ["Seniority unclear", "No mention of SQL"],
        },
    ]

    dummy_cv_paths = [
        "data/digests/cv_acme-fintech_2026-04-01.md",
        "data/digests/cv_startupxyz_2026-04-01.md",
        None,
    ]

    path = create_digest(dummy_jobs, dummy_cv_paths, total_jobs_fetched=142)
    print(f"[digest] Test complete. Output: {path}")

    print("\n--- Preview ---\n")
    print(Path(path).read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
