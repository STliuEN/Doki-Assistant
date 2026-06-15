# User Model Order Plan

## Goal

Keep the project `.env` model as the only fixed first option, while preserving user model order.

## Changes

- Remove user model sorting by `is_default`.
- Keep the system `.env` default model fixed as the first row/option.
- Keep user-created models after the system default.
- A user model marked as default should show a label, but should not move to the top.
