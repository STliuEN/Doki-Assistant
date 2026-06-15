# Model Config Fix Test Record

## Passed

Frontend targeted TypeScript check:

```powershell
cd front
npx tsc --noEmit --pretty false --ignoreConfig --jsx react-jsx --moduleResolution bundler --module esnext --target es2022 src\pages\ModelSettings.tsx src\pages\AIChat.tsx src\api\modelConfig.ts
```

Backend compile check:

```powershell
cd backend
uv run python -m compileall app
```

Backend route/method check:

```powershell
cd backend
uv run python -c "from main import app; print([(r.path, sorted(getattr(r, 'methods', []))) for r in app.routes if str(getattr(r, 'path', '')).startswith('/model-config')])"
```

Confirmed routes:

- `GET /model-config/list`
- `GET /model-config/default`
- `POST /model-config/create`
- `PUT /model-config/{config_id}`
- `DELETE /model-config/{config_id}`
- `POST /model-config/{config_id}/set-default`
- `POST /model-config/test`
- `POST /model-config/{config_id}/test`
