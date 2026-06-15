# System Default Model Row Test Record

## Backend Compile Check

Command:

```powershell
cd backend
uv run python -m compileall app
```

Result:

- Passed.

## Backend Route Check

Command:

```powershell
cd backend
uv run python -c "from main import app; print([(r.path, sorted(getattr(r, 'methods', []))) for r in app.routes if str(getattr(r, 'path', '')).startswith('/model-config')])"
```

Result:

- Passed.
- Confirmed `/model-config/system-default` and `/model-config/system-default/test` are registered before dynamic config routes.

## Frontend Targeted Type Check

Command:

```powershell
cd front
npx tsc --noEmit --pretty false --ignoreConfig --jsx react-jsx --moduleResolution bundler --module esnext --target es2022 src\pages\ModelSettings.tsx src\pages\AIChat.tsx src\api\modelConfig.ts src\api\endpoints.ts src\types\api.ts
```

Result:

- Passed.
