"""
Data ingestion module for the Podman Agentic CI Flake Categorization prototype.

This module talks to the GitHub Actions REST API to find recently failed
jobs on Podman's `ci` workflow and pull their raw logs for downstream
categorization.

Important constraint discovered while building this prototype
----------------------------------------------------------------
GitHub's `GET /repos/{owner}/{repo}/actions/jobs/{job_id}/logs` endpoint
returns HTTP 403 ("Must have admin rights to Repository") for unauthenticated
or read-only requests, even on a fully public repository. Log *listing* and
*run/job metadata* (status, conclusion, timing, names) are open, but the raw
log text itself requires a token with at least read access to Actions on the
repo (a fine-grained PAT with "Actions: Read" is enough; a full classic PAT
also works). This matters for the real project: the ingestion pipeline can't
be built as a fully anonymous public scraper, it needs a scoped bot token,
which has implications for how this tool would be deployed for the Podman
maintainers (e.g. as a scheduled GitHub Action using GITHUB_TOKEN, which
already has the right permissions inside the repo's own CI).

Usage
-----
    export GITHUB_TOKEN=ghp_xxx   # needs 'actions:read' on the target repo
    python fetch_flaky_runs.py --repo podman-container-tools/podman --limit 10
"""

import argparse
import os
import sys
import time
import urllib.request
import urllib.error
import json

API_ROOT = "https://api.github.com"


def _headers():
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "podman-flake-triage-prototype",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _get_json(url, retries=3):
    for attempt in range(retries):
        req = urllib.request.Request(url, headers=_headers())
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (403, 429) and attempt < retries - 1:
                wait = 2 ** (attempt + 1)
                print(
                    f"[_get_json] {e.code} on {url}, backing off {wait}s "
                    f"(attempt {attempt + 1}/{retries})...",
                    file=sys.stderr,
                )
                time.sleep(wait)
                continue
            raise


def list_failed_runs(repo, limit=10, workflow_name="ci"):
    """Return recent workflow runs that finished with conclusion=failure."""
    url = f"{API_ROOT}/repos/{repo}/actions/runs?status=failure&per_page={limit}"
    data = _get_json(url)
    runs = [r for r in data.get("workflow_runs", []) if r.get("name") == workflow_name]
    return runs[:limit]


def list_failed_jobs(repo, run_id):
    """Return the individual jobs within a run that failed."""
    url = f"{API_ROOT}/repos/{repo}/actions/runs/{run_id}/jobs"
    data = _get_json(url)
    return [j for j in data.get("jobs", []) if j.get("conclusion") == "failure"]


def fetch_job_log(repo, job_id):
    """Download the raw log text for a single failed job.

    Requires GITHUB_TOKEN with actions:read. Returns None (with a clear
    stderr message) if no token is configured or access is denied, rather
    than failing the whole pipeline.
    """
    url = f"{API_ROOT}/repos/{repo}/actions/jobs/{job_id}/logs"
    req = urllib.request.Request(url, headers=_headers())
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        if e.code == 403:
            print(
                f"[fetch_job_log] 403 for job {job_id}: log download needs an "
                "authenticated token with actions:read on this repo (see module "
                "docstring). Skipping raw log; metadata-only mode.",
                file=sys.stderr,
            )
            return None
        raise


def collect(repo, limit):
    """End-to-end: find failed runs, their failed jobs, and logs where available."""
    results = []
    for run in list_failed_runs(repo, limit=limit):
        time.sleep(1.0)  # avoid GitHub's secondary/abuse rate limiting
        for job in list_failed_jobs(repo, run["id"]):
            log_text = fetch_job_log(repo, job["id"])
            results.append(
                {
                    "run_id": run["id"],
                    "run_title": run.get("display_title"),
                    "job_id": job["id"],
                    "job_name": job["name"],
                    "html_url": job.get("html_url"),
                    "log_text": log_text,  # may be None if unauthenticated
                }
            )
            time.sleep(0.3)  # be polite to the API / avoid secondary rate limits
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="podman-container-tools/podman")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--out", default="flaky_jobs.json")
    args = parser.parse_args()

    print(f"Scanning last {args.limit} failed '{args.repo}' CI runs...")
    records = collect(args.repo, args.limit)
    with open(args.out, "w") as f:
        json.dump(records, f, indent=2)

    with_logs = sum(1 for r in records if r["log_text"])
    print(f"Found {len(records)} failed jobs ({with_logs} with downloaded logs).")
    print(f"Wrote {args.out}")
