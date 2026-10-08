# Failed chat request retry

## Why

When a chat job fails, users need to retry the exact request without copying it into the composer and sending it manually. The current input draft should not be lost.

## Goal

Retry a failed turn immediately through the normal submission pipeline, while keeping the conversation panel visible and preserving any draft in the composer.

Out of scope: changing retry policy, job identifiers, backend behavior, or the request text.

## What

- A retry button submits the failed turn's original request immediately.
- The retry creates a new normal job and conversation turn through the existing submit handler.
- During retry, the current composer draft remains unchanged and the mobile view stays on the conversation panel.
- A regular user submission keeps its current behavior.

## How

- `ConversationPanel` calls the retry callback with `turn.request`.
- The page routes that callback to the existing `submit` handler with an explicit retry option.
- The handler skips composer clearing and reference-panel navigation only for retry submissions.
- Retry uses existing validation, session selection, API submission, and polling.

## AC

- Given a failed turn and text in the composer, When the user selects retry, Then the original request is submitted without filling or clearing the composer.
- Given a failed turn on a narrow screen, When the user selects retry, Then the conversation panel remains visible while the request is processed.
- Given a normal request submission, When it succeeds, Then the existing behavior still clears the composer and opens the reference panel.
