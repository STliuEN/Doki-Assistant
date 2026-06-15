# User Model Order Test Record

## Backend Compile Check

Command:

```powershell
cd backend
uv run python -m compileall app
```

Result:

- Passed.

## Frontend Targeted Type Check

Command:

```powershell
cd front
npx tsc --noEmit --pretty false --ignoreConfig --jsx react-jsx --moduleResolution bundler --module esnext --target es2022 src\pages\ModelSettings.tsx src\pages\AIChat.tsx src\api\modelConfig.ts src\api\endpoints.ts src\types\api.ts
```

Result:

- Passed.
