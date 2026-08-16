# Pre-task: Agentic CI Flake Categorization for Podman

## What I built

Two small Python modules that together form a minimal, working slice of what
the full mentorship project describes:

1. `fetch_flaky_runs.py`, the data ingestion piece. It talks to the real
   GitHub Actions API for `podman-container-tools/podman`, finds recent
   failed `ci` workflow runs, and drills into which specific jobs failed.

2. `categorize.py`, the analysis piece. It classifies a failure log into a
   root cause bucket (network timeout, healthcheck timing flake, cache or
   infra blip, parallel race condition, or unclassified) with a plain
   English explanation.

## What I actually verified, not just wrote

I ran `fetch_flaky_runs.py` against Podman's live CI and it correctly
pulled real, current failed runs and identified the specific failed job
inside them (for example, job `95065533541`, `int remote root fedora-prior
/ lima`, inside a real recent failed run).

I ran `categorize.py` against real log excerpts taken from four currently
open Podman issues (#23263, #29353, #28893, and a synthetic real-bug
control case) and it classified all four correctly, including correctly
refusing to label the real bug as a flake.

## Two real constraints I ran into, and why they matter

1. **GitHub's job log download endpoint requires authentication.**
   `GET /actions/jobs/{id}/logs` returns 403 even for a fully public repo
   unless the request carries a token with `actions:read`. This means the
   ingestion pipeline cannot be a fully anonymous scraper. It has practical
   implications for how the finished tool would be deployed for Podman's
   maintainers: most naturally as a scheduled GitHub Action inside the repo
   itself, where `GITHUB_TOKEN` already has the right scope, rather than an
   external service polling from outside.

2. **Unauthenticated requests hit GitHub's rate limit fast.** 60 requests
   per hour is not enough to scan CI history at any real scale. This
   confirms the eventual tool needs a dedicated token, and probably some
   caching or webhook based triggering (react to `workflow_run` completed
   events) instead of polling.

Neither of these is a blocker, they're exactly the kind of thing you only
find by actually running the thing against the real API, not by reading the
issue description.

## How the categorization rules were built

Not guessed. Each pattern in `categorize.py` is traced to a specific, real,
currently open Podman flake issue: the network timeout pattern comes from
#23263, the healthcheck pattern from #29353, the cache and infra pattern
from #28893. That's a deliberate choice: a rule based baseline grounded in
real failures gives something to actually compare an LLM based classifier
against later, which is the core empirical question this mentorship is
about.

## What I'd propose for the full mentorship

Extend this into the three outcomes in the project description:

- **Ingestion**: move from polling to a `workflow_run` webhook, and add the
  scoped token setup so log text is actually available, not just metadata.
- **Analysis**: keep the rule based classifier as a fast first pass, and add
  an LLM call as a fallback specifically for the `unclassified` bucket, so
  every new failure pattern either gets caught by an existing rule or
  becomes a candidate for a new one, reviewed by a human before being
  trusted.
- **Reporting**: turn classification results into either a weekly digest
  issue or a PR comment, using the existing GitHub API access this
  prototype already has working.

Kavaljeet Singh
Relevant files: fetch_flaky_runs.py, categorize.py
