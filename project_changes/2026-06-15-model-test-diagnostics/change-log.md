# Model Test Diagnostics Change Log

## Backend

- Disabled local LangSmith tracing through `backend/.env`.
- Removed the Agent stream entrypoint's `@traceable` wrapper so local chat requests do not POST traces to LangSmith.
- Kept RAG tracing untouched because the observed failure came from the Agent chat path.
- Changed AI chat model selection semantics:
  - Empty `model_config_id` now means the system `.env` default model.
  - A non-empty `model_config_id` still uses the selected user model config.
- Added OpenAI-compatible base URL normalization:
  - `https://example.com` becomes `https://example.com/v1`.
  - `https://example.com/v1` stays unchanged.
- Model test endpoints now return structured diagnostics:
  - `ok`
  - `result`
  - `error`

## Frontend

- Model settings test actions display backend diagnostic details instead of only a generic failure message.
- AI chat keeps `默认配置` as the first selector option.
- User-created model config types remain limited to:
  - `通用`
  - `Ollama 本地`

## Behavior Notes

- LangSmith `403 Forbidden` was caused by invalid or placeholder tracing credentials.
- `Your request was blocked` is returned by the selected model provider. It is not a FastAPI routing error.
- If `默认配置` is selected in AI chat, the backend now uses the `.env` model configuration directly.
