# Author Policy — xPyD-proxy

Rules for the automated author bot when opening and maintaining PRs.
Read `ENTRY.md` first for general rules and `DESIGN_PRINCIPLES.md` for
architecture constraints.

---

## Identity

Bot-authored PRs use the **hlin99** token (the repo owner account).

## Branch Rules

- **Never push directly to `main`.** All changes go through a PR.
- Branch from the latest `main`. Keep the branch up-to-date by merging `main`
  into it (not rebasing).
- **Each PR must be independent** — based on the latest `main`, with no
  dependencies between PRs.
- **Avoid force-push.** Always push new commits. Force-push destroys review
  history.
- Use descriptive branch names: `fix/issue-12-error-handling`,
  `feat/add-metrics`, `test/concurrent-edge-cases`.

## Before Pushing

1. **Run pre-commit hooks** — `pre-commit run --all-files`.
2. **Run the full test suite** — `python -m pytest tests/ -v`.
3. **Run linters** — `ruff check .` and `isort --check-only --skip xpyd .`.
4. All three must pass locally before pushing.

## Commit Messages

Follow conventional commits:

```
<type>: <short description>

[optional body]
[optional footer]
```

Types: `fix`, `feat`, `test`, `docs`, `refactor`, `chore`, `ci`.

## Commit Identity

All commits must use:
```
git -c user.name="hlin99" -c user.email="tony.lin@intel.com" commit -s
```

Rules:
- Always use `tony.lin@intel.com` as the commit email.
- Never use the GitHub noreply address.
- Always include `Signed-off-by` trailer (`-s` flag) for DCO compliance.
- Never add `Co-authored-by` trailers.

## PR Description

- Clearly state **what** changed and **why**.
- Reference related issues (e.g. `closes #12`).
- If modifying `xpyd/`, explicitly call it out and explain the necessity.

## Responding to Reviews

- Address all `REQUEST_CHANGES` feedback before requesting re-review.
- Always push new commits to address feedback — do not amend or force-push.
- **Reply to each addressed review comment** with a reference to the fix
  commit (e.g. "Fixed in `abc1234`.").
- **Re-request review** after pushing fixes.
- Keep PRs focused — one concern per PR.

## Active PR Maintenance

This section applies in **triggered mode** (not a continuous loop). The
maintenance workflow is invoked by a cron or heartbeat trigger — it does not
run autonomously in the background.

When triggered, for each open (non-draft) bot-authored PR:

1. **Update branch** — if the PR branch is behind `main`, merge `main` into
   the branch. PRs must always be up-to-date with `main`.
2. **CI check** — check CI status. If any check has failed, examine the
   failure logs, fix the code, and push a new commit. Do not wait for
   reviewers to point out CI failures — fix them proactively.
3. **Review comment check** — read any `CHANGES_REQUESTED` reviews or
   inline comments. Even if a later reviewer submitted `APPROVE`, examine
   every `CHANGES_REQUESTED` review and verify the issues have been
   addressed. For each piece of feedback:
   - Fix the code accordingly.
   - Run pre-commit, tests, and linters locally before pushing.
   - Push a new commit (not amend/force-push).
   - Reply to each addressed comment referencing the fix commit.
4. **Re-request review** — after pushing fixes, re-request review from the
   reviewer(s) who requested changes.

**No force-push.** Force-pushing destroys review context. Always push new
commits.
