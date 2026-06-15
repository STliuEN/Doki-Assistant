# Model Config Fix Change Log

## Implemented

- Removed `default` from the editable model type selector on the model settings page.
- AI chat model selector still keeps `默认配置` as the first option.
- AI chat now starts with `默认配置` selected instead of auto-selecting a saved default.
- Rewrote `ModelSettings.tsx` text and form markup to fix broken display text.
- Added a `测试连接` button for the current unsaved/edited form.
- Kept per-row saved config connection testing.
- Improved delete flow:
  - passes the full config object
  - blocks deleting default/system type configs
  - refreshes the list after delete
  - resets the form if the deleted item was being edited
- Backend now rejects user-created or user-updated `default` model configs.
- Backend still keeps `default` internally for system fallback behavior.

## Files Changed

- `front/src/pages/ModelSettings.tsx`
- `front/src/pages/AIChat.tsx`
- `backend/app/services/model_config_service.py`
