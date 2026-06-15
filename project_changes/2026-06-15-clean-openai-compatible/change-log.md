# Clean OpenAI-Compatible Calls Change Log

## Backend

- Added `backend/app/utils/clean_openai_chat.py`.
- Replaced `langchain_openai.ChatOpenAI` for user-created `openai_compatible` configs.
- `openai_compatible` now uses `httpx` directly with clean headers:
  - `Authorization`
  - `Content-Type`
  - `Accept`
  - browser-like `User-Agent`
- Avoids OpenAI SDK headers such as:
  - `AsyncOpenAI/Python ...`
  - `X-Stainless-*`
- Keeps LangChain Agent compatibility:
  - supports `bind_tools`
  - sends OpenAI-style `tools`
  - parses returned `tool_calls`

## Compatibility Notes

- This keeps the provider type as `openai_compatible`.
- The expected provider endpoint is still Chat Completions:
  - `{base_url}/chat/completions`
- For su8 Chat Completions, use:
  - `https://www.su8.codes/v1`
- Do not use the Codex Responses endpoint as this model type's base URL.
