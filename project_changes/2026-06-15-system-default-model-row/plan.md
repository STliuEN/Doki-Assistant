# System Default Model Row Plan

## Goal

Make the project's built-in default model visible and fixed as the first model option.

## Changes

- Add backend APIs for reading and testing the project default model from environment variables.
- Show the project default model as the first row in model settings.
- Make the project default row read-only.
- Keep user-created model configs after the project default row.
- Make Ollama mode default to `http://localhost:11434` when selected.
