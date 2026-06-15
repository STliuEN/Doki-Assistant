# README Architecture Update Change Log

## README

- Added `项目架构` section.
- Added Mermaid architecture diagram.
- Documented model call architecture:
  - project `.env` default model
  - user model configs
  - OpenAI-compatible clean HTTP caller
  - Ollama local model path
- Documented model settings page behavior:
  - first row is the project default model
  - user models start from the second row
  - Ollama reads local `/api/tags`
- Updated backend technical stack with the clean OpenAI-compatible caller.
- Updated project structure for:
  - `model_config.py`
  - `model_config_router.py`
  - `model_config_service.py`
  - `clean_openai_chat.py`
  - `model_provider.py`
  - `front/src/api/modelConfig.ts`
  - `front/src/pages/ModelSettings.tsx`
- Updated LLM configuration notes.
