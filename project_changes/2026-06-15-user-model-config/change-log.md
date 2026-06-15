# User Model Config Change Log

## Implemented

- Added per-user model config persistence in the FastAPI backend.
- Added `user_model_configs` table.
- Added model config CRUD APIs:
  - `GET /model-config/list`
  - `GET /model-config/default`
  - `POST /model-config/create`
  - `PUT /model-config/{config_id}`
  - `DELETE /model-config/{config_id}`
  - `POST /model-config/{config_id}/set-default`
  - `POST /model-config/test`
  - `POST /model-config/{config_id}/test`
- Added model types:
  - `default`
  - `ollama`
  - `openai_compatible`
- Added API key encryption/masking helpers.
- Added OpenAI-compatible chat model creation through `langchain-openai`.
- Added `model_config_id` to AI chat stream requests.
- AI chat now uses the selected user model config when provided.
- If no model config is selected, AI chat uses the current user's default config.
- If no user default config exists, AI chat falls back to the existing `.env` model behavior.
- Added frontend model settings page at `/model-settings`.
- Added a sidebar item named `模型选择`.
- Added model selection dropdown to the AI chat input area.
- Added Vite proxy for `/model-config/`.

## Files Added

- `backend/app/models/model_config.py`
- `backend/app/router/model_config_router.py`
- `backend/app/schemas/model_config.py`
- `backend/app/services/model_config_service.py`
- `backend/app/utils/crypto_utils.py`
- `backend/app/utils/model_provider.py`
- `front/src/api/modelConfig.ts`
- `front/src/pages/ModelSettings.tsx`

## Dependency Changes

- Added `langchain-openai` to `backend/pyproject.toml`.
- Ran `uv sync` in `backend`.

## Verification

- `uv run python -m compileall app` passed in `backend`.
- `from main import app` passed and `/model-config/list` route is registered.
- `init_db()` ran successfully and created `user_model_configs`.
- Targeted TypeScript check passed for:
  - `src/pages/ModelSettings.tsx`
  - `src/pages/AIChat.tsx`
  - `src/api/modelConfig.ts`

## Known Existing Issue

- Full frontend `npm run build` still fails due pre-existing TypeScript errors in `NoteEditor.tsx` and `NoteList.tsx`.
- These errors are unrelated to this model config change.
