# User Model Order Change Log

## Backend

- Changed user model config list ordering from:
  - `is_default DESC, created_at DESC`
- To:
  - `created_at DESC`

## Frontend

- Removed the extra frontend sort that moved user default models to the front.
- Model settings now renders:
  - first row: project `.env` default model
  - following rows: user-created models in backend order
- AI chat model selector keeps:
  - first option: project `.env` default model
  - following options: user-created models in backend order
