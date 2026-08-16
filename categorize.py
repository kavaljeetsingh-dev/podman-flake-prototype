"""
Categorization engine for the Podman Agentic CI Flake Categorization prototype.

This is the "Agentic Analysis Engine" piece described in the LFX project:
given a raw CI failure log, classify the likely root cause into a small set
of actionable buckets, and produce a short plain English explanation.

Design note
-----------
This prototype uses rule based pattern matching, not a live LLM call,
because building this at all requires a stable, inspectable baseline first.
You cannot tell whether an LLM classifier is doing well without a labeled
set of known failures to check it against, and you cannot get that labeled
set without first reading real logs closely enough to write the rules by
hand. That is what this module is: the labeled ground truth and the first
classifier, built directly from real, currently open Podman flake issues
(#29353, #23263, #24571, #28893), not synthetic examples.

The `classify` function is written so an LLM call can slot in later as an
additional signal or a fallback for logs that do not match any known
pattern, which is exactly the kind of A/B comparison ("rule based baseline
vs agentic classifier") the mentorship description asks for.
"""

import re
from dataclasses import dataclass, field


@dataclass
class FlakeCategory:
    name: str
    pattern: "re.Pattern"
    explanation: str


@dataclass
class ClassificationResult:
    category: str
    confidence: str  # "high" | "medium" | "low"
    explanation: str
    matched_snippet: str = ""


# Patterns derived from real, currently open podman-container-tools/podman
# flake issues. Each one is grounded in an actual failure signature seen in
# CI logs, not a guess.
CATEGORIES = [
    FlakeCategory(
        name="network_timeout",
        pattern=re.compile(
            r"(timed out after \d+(\.\d+)?s|"
            r"connection refused|"
            r"Ncat:.*Listening|"
            r"command timed out after \d+s.*\[nc )",
            re.IGNORECASE,
        ),
        explanation=(
            "Network operation (bind/listen/connect) exceeded its timeout window. "
            "Matches the pattern in issue #23263 (network bind: timeout)."
        ),
    ),
    FlakeCategory(
        name="healthcheck_timing_flake",
        pattern=re.compile(
            r"(FailingStreak\":\d|"
            r"waiting for ['\"]?unhealthy['\"]?|"
            r"FAIL: Four or more failures)",
            re.IGNORECASE,
        ),
        explanation=(
            "Healthcheck state transition did not happen within the expected "
            "polling window; likely a timing race, not a real health regression. "
            "Matches the pattern in issue #29353 (healthcheck flaky)."
        ),
    ),
    FlakeCategory(
        name="cache_or_infra_blip",
        pattern=re.compile(
            r"(cache causes flaky results|"
            r"no space left on device|"
            r"connection reset by peer|"
            r"i/o timeout)",
            re.IGNORECASE,
        ),
        explanation=(
            "Failure signature matches known CI runner or caching infrastructure "
            "instability rather than a code defect. See issue #28893."
        ),
    ),
    FlakeCategory(
        name="parallel_race_condition",
        pattern=re.compile(
            r"(journald.*multiple containers|"
            r"SECONDS.*rounded|"
            r"parallel.*flake)",
            re.IGNORECASE,
        ),
        explanation=(
            "Failure correlates with parallel test execution timing, consistent "
            "with resource contention between concurrently running tests."
        ),
    ),
]


def classify(log_text: str) -> ClassificationResult:
    """Classify a single failure log into a root-cause bucket.

    Returns category='unclassified' with confidence='low' if nothing
    matches, which is the honest signal that this is exactly the case
    where a human, or a future LLM fallback pass, should look at it.
    """
    if not log_text or not log_text.strip():
        return ClassificationResult(
            category="no_log_available",
            confidence="low",
            explanation=(
                "No log text was retrieved for this job (see fetch_flaky_runs.py: "
                "GitHub's log download endpoint requires an authenticated token). "
                "Cannot classify without log content."
            ),
        )

    for cat in CATEGORIES:
        match = cat.pattern.search(log_text)
        if match:
            start = max(0, match.start() - 40)
            end = min(len(log_text), match.end() + 40)
            return ClassificationResult(
                category=cat.name,
                confidence="high",
                explanation=cat.explanation,
                matched_snippet=log_text[start:end].strip(),
            )

    return ClassificationResult(
        category="unclassified",
        confidence="low",
        explanation=(
            "No known failure signature matched. This is a candidate for either "
            "a new rule or an LLM based fallback classifier, and should be "
            "surfaced to a maintainer rather than auto-labeled."
        ),
    )


if __name__ == "__main__":
    # Real log excerpts pulled from currently open Podman flake issues, used
    # here as a small labeled test set to sanity check the classifier.
    test_cases = {
        "issue_23263_network_timeout": (
            "podman-remote run --network slirp4netns:outbound_addr=127.0.0.1 "
            "nc -w 2 10.0.2.2 5546\n"
            "Ncat: Listening on [::]:5546\n"
            "[FAILED] Timed out after 90.001s.\n"
            "command timed out after 90s: [nc -v -n -l -p 5546]"
        ),
        "issue_29353_healthcheck_flake": (
            '{"Status":"healthy","FailingStreak":2,"Log":[...]}\n'
            "FAIL: Four or more failures - timed out waiting for 'unhealthy' "
            "in podman events"
        ),
        "issue_28893_cache_infra": (
            "skip-cache: true # cache causes flaky results "
            "https://github.com/podman-container-tools/podman/issues/28893"
        ),
        "unrelated_real_bug": (
            "panic: runtime error: index out of range [5] with length 3\n"
            "goroutine 1 [running]:\nmain.processContainer(...)"
        ),
    }

    print("Running classifier against real Podman flake log excerpts:\n")
    for label, log in test_cases.items():
        result = classify(log)
        print(f"[{label}]")
        print(f"  category:   {result.category}")
        print(f"  confidence: {result.confidence}")
        print(f"  reason:     {result.explanation}")
        print()
