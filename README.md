# Podman Agentic CI Flake Categorization (Prototype)

A small, working prototype built for the CNCF LFX Mentorship 2026 Term 3
project ["Agentic CI Flake Categorization and
Analysis"](https://mentorship.lfx.linuxfoundation.org/project/050e89d9-aec2-47ad-9113-3ba41a639d55)
for Podman.

The full project aims to build a system that watches Podman's GitHub Actions
CI, automatically identifies flaky test failures, and uses an AI agent to
explain why they likely failed. This repo is a small, verified slice of
that system: real data in, real classification out, tested against actual
Podman CI failures.

## What's here

| File | Purpose |
|---|---|
| `fetch_flaky_runs.py` | Talks to the GitHub Actions API to find recent failed CI runs and jobs for `podman-container-tools/podman`. |
| `categorize.py` | Classifies a failure log into a root cause bucket (network timeout, healthcheck flake, infra blip, race condition, or unclassified). |
| `PRE_TASK.md` | Write-up of what was built, what was verified against real data, and two real constraints discovered along the way. |

## Quick start

```bash
# 1. Fetch recent failed CI runs and jobs (metadata works without a token;
#    raw log download needs a GitHub token with actions:read)
export GITHUB_TOKEN=ghp_xxx   # optional, but required for full log text
python fetch_flaky_runs.py --repo podman-container-tools/podman --limit 10

# 2. See the classifier in action against real, known flake log excerpts
python categorize.py
```

Example classifier output:

```
[issue_23263_network_timeout]
  category:   network_timeout
  confidence: high
  reason:     Network operation (bind/listen/connect) exceeded its timeout
              window. Matches the pattern in issue #23263.

[unrelated_real_bug]
  category:   unclassified
  confidence: low
  reason:     No known failure signature matched. Should be surfaced to a
              maintainer rather than auto-labeled.
```

## Why rule based, not an LLM call, for now

A classifier is only as trustworthy as the ground truth it's checked
against. Before wiring up an LLM, this prototype first builds a small,
hand verified baseline from real, currently open Podman flake issues
(#23263, #29353, #28893). That baseline is what a future LLM based
classifier should be A/B tested against, not guessed at from scratch.
Full reasoning in `PRE_TASK.md`.

## What running this against the real API surfaced

Two constraints that only show up when you actually call the API, not
when you read the project description:

1. GitHub's job log download endpoint (`/actions/jobs/{id}/logs`) returns
   403 without an authenticated token, even on a public repo.
2. Unauthenticated requests hit GitHub's rate limit fast (60/hour), which
   rules out naive polling at any real scale.

Both have direct implications for how the finished tool should be
deployed. Details in `PRE_TASK.md`.

## Status

This is a pre-application prototype, not a submitted pull request. It
exists to show a working, tested starting point for the mentorship
proposal above.

## Author

Kavaljeet Singh
GitHub: [github.com/kavaljeetsingh-dev](https://github.com/kavaljeetsingh-dev)
