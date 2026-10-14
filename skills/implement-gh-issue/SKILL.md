
---
name: implement-issue
description: Implement an existing GitHub issue according to its approved implementation plan. Includes coding, testing, and verification. Never commit, push, or create pull requests.
---

# Implement GitHub Issue

## Purpose

Implement an existing GitHub issue that already contains a concrete, approved implementation plan.

Focus on execution, code quality, and verification rather than unnecessary replanning.

## Input

The user provides a GitHub issue number or URL.

If no issue is provided, ask for one before proceeding.

## Workflow

### 1. Understand the issue

- Fetch and read the complete GitHub issue, including relevant comments.
- Identify the requirements, implementation steps, and acceptance criteria.
- Treat the approved implementation plan as the source of truth.
- Inspect relevant repository files and existing architecture.
- Check repository instructions, conventions, and available tooling.
- Do not redesign the solution unless technically necessary.

### 2. Implement

- Check out the main branch and ensure the working tree is clean.
- Create a new branch for the implementation.
- Execute the implementation plan systematically.
- Follow existing architecture, naming conventions, and coding style.
- Reuse existing components and utilities whenever possible.
- Keep changes focused on the issue.
- Avoid unrelated refactoring, speculative features, or unnecessary dependencies.
- Implement all applicable acceptance criteria.
- Do not stop after planning. Complete the implementation.

### 3. Test

- Add or update relevant automated tests.
- Run existing tests affected by the changes.
- Run available linting, formatting checks, and type checks.
- Run the build where applicable.
- Fix failures introduced by the implementation.
- Do not silently ignore failing checks.
- Do not modify unrelated tests merely to make checks pass.

### 4. Verify

- Compare the final implementation against the GitHub issue.
- Verify every acceptance criterion.
- Review the diff for unintended modifications.
- Check for regressions and obvious edge cases.
- Ensure no secrets, credentials, or temporary debugging artifacts were introduced.
- Use browser-based verification when relevant and available.

### 5. Report

Provide a concise final report containing:

1. **Implementation:** What was changed and why.
2. **Files:** Important files added or modified.
3. **Verification:** Tests, checks, and their results.
4. **Acceptance criteria:** Completed and incomplete criteria.
5. **Deviations:** Any departures from the original plan.
6. **Remaining work:** Known limitations or unresolved issues.

## Strict Git Restrictions

The following operations are prohibited unless the user explicitly authorizes them in a subsequent instruction:

- Do NOT create Git commits.
- Do NOT amend existing commits.
- Do NOT push changes to any remote.
- Do NOT create or update pull requests.
- Do NOT create tags or releases.
- Do NOT create or switch branches automatically.
- Do NOT stage files using `git add`.
- Do NOT modify the GitHub issue or its comments.
- Do NOT perform destructive Git operations such as reset, clean, or checkout that discard changes.

All implementation changes must remain uncommitted in the current working tree.

Read-only Git operations such as `git status`, `git diff`, and `git log` are allowed.

Preserve any pre-existing user changes in the working tree.

## Autonomy and Decision Making

- Work autonomously within the approved scope.
- Do not request confirmation for routine implementation decisions.
- Prefer existing project patterns over introducing new abstractions.
- If a minor ambiguity exists, choose the simplest reasonable solution and document the assumption.
- If a major ambiguity, security concern, or technical blocker prevents safe implementation, ask the user before proceeding.
- Never silently deviate from an explicit requirement.
- Do not claim tests passed unless they were actually executed.
- Do not claim acceptance criteria are complete without verification.

## Completion Criteria

The task is complete when:

- All feasible requirements have been implemented.
- Relevant tests and checks have been executed.
- Failures introduced by the implementation have been resolved.
- The changes have been reviewed against the issue.
- A final implementation report has been provided.
- All changes remain uncommitted and unpushed.

Stop after reporting. Wait for the user's review and further instructions.
