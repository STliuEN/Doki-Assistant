# E3 isolated MySQL topology

This directory is the only compose definition allowed for the E3 auth batch.
It creates `doki-e3-20260831-mysql`, `doki-e3-20260831-mysql-restore`, and
`doki-e3-20260831-net` on loopback ports `33327` and `33328`.

Set the two local-only environment variables before starting the topology;
they are consumed by Compose and must never be committed or pasted into logs.
E1/E2 resources are intentionally absent from this compose file.

```powershell
$env:E3_MYSQL_ROOT_PASSWORD = '<local-only-root-password>'
$env:E3_MYSQL_PASSWORD = '<local-only-app-password>'
docker compose up -d
docker compose ps
```

Use `E3_DATABASE_URL` with the dedicated `doki_e3_app` user only after both
health checks are green. The application migration guard remains responsible
for checking the exact server UUID, SQL mode, packet size, and isolation.
