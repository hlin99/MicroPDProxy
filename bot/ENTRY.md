# Bot Policy — xPyD-proxy

This directory contains the rules that automated bots must follow when
operating on this repository. Human contributors should refer to
`CONTRIBUTING.md`.

## Files

| File | Purpose |
|---|---|
| `ENTRY.md` | This file — overview and navigation. |
| `REVIEW_POLICY.md` | Rules for reviewing PRs (reviewer bots). |
| `AUTHOR_POLICY.md` | Rules for authoring PRs (author bot). |
| `DESIGN_PRINCIPLES.md` | Architecture constraints and design rules. |

## Before Any Action

- **Always fetch latest `main`** and re-read these files. They change
  frequently. Never rely on cached copies.
- For task design details, refer to the linked GitHub Issue in the PR
  description.

## General Rules

- **English only** — all content on GitHub must be in English. This includes
  code, comments, commit messages, PR titles/descriptions, review comments,
  and inline annotations. No Chinese characters allowed.
- **Secrets** — never hardcode tokens or credentials in code, PR descriptions,
  or bot prompts. Read from secure storage at runtime.
- **Scope** — bots should limit their actions to reviewing code and authoring
  PRs. No issue triage, no label management, no branch deletion unless
  explicitly configured.
- **Transparency** — every bot action should produce a brief summary of what
  it did (or chose not to do) for audit purposes.
