# System Default Model Row Change Log

## Backend

- Added `GET /model-config/system-default`.
- Added `POST /model-config/system-default/test`.
- The system default config is read from `.env`:
  - `LLM_TYPE`
  - `ALIYUN_MODEL_NAME` / `CHAT_MODEL_NAME`
  - `ALIYUN_BASE_URL`
  - `OLLAMA_MODEL_NAME`
  - `OLLAMA_BASE_URL`

## Frontend

- Model settings now renders the project default model as the first row.
- The project default row is read-only:
  - no edit
  - no delete
  - no set-default action
- The project default row can still be tested.
- AI chat model selector now labels the first option as `工程默认配置`.
- Selecting `Ollama 本地` now resets the Ollama address to `http://localhost:11434`.
