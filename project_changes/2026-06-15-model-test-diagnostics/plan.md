# Model Test Diagnostics Plan

## Goal

Make model testing and chat failures diagnosable.

## Observed Problems

- LangSmith tracing returns `403 Forbidden` because the local key/project is not valid.
- The actual selected model returns `Your request was blocked`.
- The model settings test UI only shows a generic failure message.
- Some OpenAI-compatible providers require a `/v1` base URL, while users may enter the root URL.

## Changes

- Disable local LangSmith tracing in `backend/.env`.
- Normalize OpenAI-compatible `base_url` by appending `/v1` when the user enters only the provider root.
- Make model test APIs return structured success/failure results instead of only throwing generic errors.
- Show the backend failure detail in the frontend model settings page.
- Make the AI chat selector's first option, `默认配置`, use the system `.env` model instead of silently using a user-marked default config.
- Remove LangSmith tracing from the local Agent stream entrypoint to avoid debug tracing failures masking model-provider errors.

## Notes

- `Your request was blocked` is from the model provider, not from FastAPI itself.
- If the provider blocks the request, the UI should display that reason clearly.
