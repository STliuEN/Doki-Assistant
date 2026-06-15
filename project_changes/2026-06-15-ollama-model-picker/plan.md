# Ollama Model Picker Plan

## Goal

Make Ollama model configuration easier and less error-prone.

## Changes

- Add a backend endpoint that reads installed Ollama models from `/api/tags`.
- In the model settings form, switch to an Ollama-specific layout when `Ollama 本地` is selected.
- Hide provider and API key fields for Ollama.
- Let users refresh and select local Ollama models from a dropdown.
- Keep OpenAI-compatible model configuration unchanged.
