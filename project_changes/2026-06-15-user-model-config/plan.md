# User Model Config Plan

## Goal

Add per-user model configuration management and allow the AI chat page to choose a model for each request.

## User-Facing Changes

- Add a new sidebar item: Model Settings.
- Add a model settings page with an editable list.
- The list columns are:
  - Model type
  - Provider
  - Model name
  - Base URL
  - API SK
- Supported model types:
  - General: OpenAI-compatible API.
  - Ollama local: local Ollama service.
  - Default config: current environment-based Aliyun/DashScope config.
- Add a model selector near the AI chat input.

## Backend Changes

- Add a `user_model_configs` table in the FastAPI backend database.
- Add CRUD APIs for current user's model configs.
- Add a connection test endpoint.
- Add model creation logic for:
  - default environment config
  - Ollama
  - OpenAI-compatible chat API
- Extend chat request schema with `model_config_id`.
- Validate that a selected config belongs to the current user.

## Frontend Changes

- Add `/model-settings` route.
- Add model settings API client.
- Add model config TypeScript types.
- Add sidebar entry under user-related menu items.
- Add model selector to the AI chat input area.
- Send `model_config_id` with chat stream requests.

## Security

- API keys should not be returned in plain text.
- API keys should be masked in list responses.
- First implementation may store the key in the backend DB for local development, but the code path should isolate it so encryption can be added cleanly.

## Scope For This Change

- Apply model selection to AI chat only.
- Keep RAG, note AI, document embedding, and background services on current global config for now.
- Keep `.env` config as fallback.

## Test Plan

- Backend imports and database initialization.
- CRUD model configs for authenticated user.
- Default config works without API SK.
- Ollama config can be saved and listed.
- OpenAI-compatible config can be saved with masked SK.
- AI chat request can include `model_config_id`.
- Existing AI chat still works without `model_config_id`.
