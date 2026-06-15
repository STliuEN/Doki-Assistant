# Clean OpenAI-Compatible Calls Plan

## Goal

Improve compatibility with OpenAI-compatible relay providers.

## Problem

- `requests` and raw `httpx` calls to su8 Chat Completions succeed.
- OpenAI SDK calls fail with `Your request was blocked`.
- Simulating the OpenAI SDK headers with raw `httpx` also returns `403`.
- The project used `langchain_openai.ChatOpenAI`, which depends on the OpenAI SDK request path.

## Changes

- Add a local LangChain chat model that calls `/chat/completions` with clean `httpx` requests.
- Preserve standard OpenAI Chat Completions request shape.
- Preserve LangChain Agent tool binding by forwarding OpenAI-style `tools` and parsing `tool_calls`.
- Route all `openai_compatible` model configs through the clean caller.
