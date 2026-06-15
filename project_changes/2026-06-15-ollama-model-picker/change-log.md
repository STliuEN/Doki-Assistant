# Ollama Model Picker Change Log

## Backend

- Added `GET /model-config/ollama/models`.
- The endpoint accepts `base_url`, defaulting to `http://localhost:11434`.
- The endpoint calls `{base_url}/api/tags` and returns:
  - `ok`
  - `base_url`
  - `models`
  - `error`

## Frontend

- Added `modelConfigApi.listOllamaModels`.
- Added `OllamaModelsResponse` type.
- Updated `ModelSettings`:
  - `Ollama 本地` mode hides provider and API SK fields.
  - `Ollama 本地` mode shows `Ollama 地址`.
  - `模型名称` becomes a dropdown populated from local Ollama models.
  - Added `刷新模型` button.
  - Saving Ollama configs automatically uses provider `ollama` and empty API key.
