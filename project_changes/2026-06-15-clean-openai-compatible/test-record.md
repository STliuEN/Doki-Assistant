# Clean OpenAI-Compatible Calls Test Record

## Backend Compile Check

Command:

```powershell
cd backend
uv run python -m compileall app
```

Result:

- Passed.

## su8 Direct Compatibility Checks

OpenAI SDK result:

- `AsyncOpenAI(...).chat.completions.create(...)` returned `403 Your request was blocked`.

Raw `httpx` result:

- Same JSON request returned `200`.

Raw `httpx` with OpenAI SDK headers:

- Returned `403 Your request was blocked`.

New clean LangChain chat model:

- Simple chat request returned `200`.
- Tool-bound chat request returned `200`.

## Conclusion

The failure was caused by OpenAI SDK-style headers being blocked by the relay provider, not by the user's model settings or Chat Completions JSON shape.
