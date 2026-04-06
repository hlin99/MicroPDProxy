# Review Policy — xPyD-proxy

Rules for automated review bots operating on this repository.
Read `ENTRY.md` first for general rules and `DESIGN_PRINCIPLES.md` for
architecture constraints.

---

## Identity

Two review bots operate on this repo:

- **hlin99-Review-Bot** — first reviewer
- **hlin99-Review-BotX** — second reviewer

Each bot uses its own dedicated token. **Never use the author's (hlin99)
token for reviews.**

## What to Review

1. **Skip draft PRs** — do not review, comment, or interact with them.
2. **Skip already-reviewed commits** — if the PR head SHA has not changed since
   your last review, do not submit a duplicate review.
3. **Re-requested reviews take priority** — if a reviewer is explicitly
   re-requested, always perform a fresh review even if the commit SHA has not
   changed.
4. **Only skip APPROVED commits** — a commit SHA is considered "reviewed" only
   if you submitted `APPROVE` on it. `COMMENT` does not count.
5. **One review per PR per commit SHA** — never submit multiple reviews for the
   same commit.

## Review Standard

Reviews must be performed to the **strictest standard**. Every line of changed
code must be examined. Do not approve unless you are confident the code is
correct.

## Review Checklist

| Area | Check |
|---|---|
| **CI** | CI does not block reviewing — start immediately. However, CI must be fully green before submitting `APPROVE`. If CI is pending or failed, you may submit `REQUEST_CHANGES` or `COMMENT`. |
| **Merge conflicts** | If `mergeable == false`, submit `REQUEST_CHANGES`. |
| **`xpyd/` changes** | Business logic and API signatures must remain intact. Topology matrix configs must not be broken. |
| **Logic errors** | Incorrect conditions, off-by-one, unhandled edge cases. |
| **Type safety** | Mismatched parameter/return types, missing `None` checks. |
| **Concurrency** | Race conditions, missing locks, shared mutable state. |
| **Exception handling** | Bare `except`, swallowed exceptions, resource leaks. |
| **Security** | Injection risks, hardcoded secrets, unsanitized input. |
| **Code style** | Unused imports, shadowed variables, unclear naming. |
| **Test coverage** | New logic must have corresponding tests. |

## Review Verdicts

- **`APPROVE`** — only if the code is correct, CI is fully green, and no issues
  are found.
- **`REQUEST_CHANGES`** — if any issue is found. Use inline comments to point
  to specific files and lines.
- **`COMMENT`** — if CI is still running or you need to note something without
  blocking.

## Merge Policy

> **Bots must NEVER merge a PR.** All merge operations are performed manually
> by a human maintainer.

This is non-negotiable.

## Review Trigger Schedule

- **Has open (non-draft) PRs**: check every **5 minutes**.
- **No open PRs**: check every **15 minutes**.
- A review can also be triggered immediately via chat command.

## Rate Limiting

Respect GitHub API rate limits; back off on `429` responses. Do not flood
PRs with duplicate comments or reviews.
