# Model Config Fix Plan

## Goal

Fix model config management after the first implementation.

## Requested Changes

- Remove `default` from the model type options on the model settings page.
- Keep the first AI chat model selector option as the system default config.
- Make connection testing clearer and usable.
- Make deletion reliable and refresh the table after deletion.

## Implementation Plan

- Frontend:
  - Rewrite `ModelSettings.tsx` text and form labels cleanly.
  - Keep only two editable model types:
    - General (`openai_compatible`)
    - Ollama local (`ollama`)
  - Add a "test current form" button.
  - Keep a "test saved config" action in the table.
  - Improve delete result handling.
- Backend:
  - Keep supporting `default` internally for fallback compatibility.
  - Reject user-created `default` model configs from the API.
  - Keep AI chat fallback behavior unchanged.

## Test Plan

- Targeted TypeScript check for changed frontend files.
- Backend import/compile check.
- Verify model-config routes are still registered.
