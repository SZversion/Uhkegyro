# AGENTS.md

These are the shared instructions for AI coding agents (Claude Code, Codex, Cursor, and others) working in this repository. Follow this document regardless of which tool you use.

## Project Overview

(To be completed by the team: a one-line description of what this project builds.)

## Tech Stack

(To be completed by the team: languages, frameworks, and primary libraries.)

## Language for User-Facing Responses

All user-facing explanations, questions, progress updates, and completion reports must be written in Korean. Keep code, commands, file paths, error messages, API names, library names, and other proper nouns in their original form when translating them would reduce precision.

## Spec First, Then Implementation

Before asking an agent to build a feature, create its Spec at `docs/specs/{feature-name}.md`. Use `docs/specs/_example.md` as the format reference. It must contain all five sections (Why, Goal, What, How, and AC) before it can be handed to an agent as-is.

- **Why**: persona, situation, problem, and metrics
- **Goal**: measurable success criteria and out-of-scope items
- **What**: happy path and edge cases
- **How**: API, data, and constraints that leave no room for arbitrary agent decisions
- **AC**: Given-When-Then format that can be translated directly into tests

## Documentation for Every Feature

Every feature must have its own document at `docs/specs/{feature-name}.md`, including a small API endpoint, UI interaction, data workflow, or user-visible behavior. Create and complete that document before writing implementation code; do not combine unrelated features in one document.

If implementation changes a feature's contract, scope, edge cases, or acceptance criteria, update its document in the same change. A feature is not complete until its document and implementation describe the same behavior.

## GitHub Pull Request Authority

Only when the user explicitly authorizes GitHub changes for the current task, an agent may commit and push its own branch and create a pull request. After creating the pull request, the agent must stop and wait for a human team member.

Agents must never approve, merge, enable auto-merge, dismiss reviews, alter branch protection, or otherwise finalize another pull request. Human team members remain solely responsible for review, approval, and merge decisions.

## Out-of-Scope Principle

Agents must not add features that are not defined in the Spec. Do not expand the scope because something seems convenient to add.

## Change Scope and Pull Request Size

- A single pull request must not contain more than 400 lines of code changes.
- Agents must modify only the files and behavior explicitly required by the assigned task. Do not make unrelated fixes, refactors, formatting changes, dependency updates, or documentation changes.
- If the requested work would exceed the 400-line limit, stop and split it into separate pull requests with clear, independently reviewable scopes.

## Definition of Done

Do not report work as complete until tests based on the acceptance criteria pass.
