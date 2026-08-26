# AR-0 隔离备份与恢复演练

本文档描述 AR-0 阶段的最小离线工具链，只用于隔离 fixture。它不连接 MySQL，不调用 `mysqldump`，不发现默认数据目录，也不会覆盖已有备份或恢复目标。真实依赖、PITR、在线一致性、应用/worker 停写和跨对象一致性仍属于后续门禁证据。

## 保护对象与产物

入口为 `backend/scripts/backup_restore.py`，支持三种对象：

| `--kind` | 输入 | 恢复目标 |
|---|---|---|
| `mysql-dump` | 已在隔离环境生成的单个 SQL dump/fixture 文件 | 新 SQL 文件 |
| `storage-tree` | 隔离 Storage fixture 目录 | 新目录 |
| `chroma-projection` | 隔离 Chroma projection fixture 目录 | 新目录 |

每个备份是只读语义的目录式 bundle：`manifest.json` 记录 schema、对象类型、格式、UTC 创建时间、相对路径、类型、字节数、逐文件 SHA-256 和内容清单 SHA-256；`payload/` 保存副本。目录清单包含空目录。

工具在备份发布前、恢复切换前执行完整校验。源、bundle、payload 中出现符号链接，manifest 出现绝对路径或 `..`，payload 缺失、多出或被修改，都会 fail-closed。输出或恢复目标已存在时也会拒绝操作。

## 隔离演练

以下命令中的路径必须指向专门创建且不含业务数据的演练目录。先在 `backend` 目录执行：

```powershell
$DrillRoot = Join-Path $env:TEMP "doki-ar0-backup-drill"
New-Item -ItemType Directory -Path $DrillRoot

$MysqlFixture = Join-Path $DrillRoot "fixture.sql"
Set-Content -LiteralPath $MysqlFixture -Value "CREATE TABLE fixture (id INT);"
uv run python scripts/backup_restore.py backup --kind mysql-dump --source $MysqlFixture --output (Join-Path $DrillRoot "mysql-backup")
uv run python scripts/backup_restore.py restore --bundle (Join-Path $DrillRoot "mysql-backup") --target (Join-Path $DrillRoot "mysql-restored.sql")
uv run python scripts/backup_restore.py verify --bundle (Join-Path $DrillRoot "mysql-backup") --target (Join-Path $DrillRoot "mysql-restored.sql")
```

Storage 和 Chroma 使用不同的隔离 fixture，命令结构相同：

```powershell
$StorageFixture = New-Item -ItemType Directory -Path (Join-Path $DrillRoot "storage-fixture")
Set-Content -LiteralPath (Join-Path $StorageFixture "object.bin") -Value "isolated storage object"
uv run python scripts/backup_restore.py backup --kind storage-tree --source $StorageFixture --output (Join-Path $DrillRoot "storage-backup")
uv run python scripts/backup_restore.py restore --bundle (Join-Path $DrillRoot "storage-backup") --target (Join-Path $DrillRoot "storage-restored")
uv run python scripts/backup_restore.py verify --bundle (Join-Path $DrillRoot "storage-backup") --target (Join-Path $DrillRoot "storage-restored")

$ChromaFixture = New-Item -ItemType Directory -Path (Join-Path $DrillRoot "chroma-fixture")
Set-Content -LiteralPath (Join-Path $ChromaFixture "chroma.sqlite3") -Value "isolated projection fixture"
uv run python scripts/backup_restore.py backup --kind chroma-projection --source $ChromaFixture --output (Join-Path $DrillRoot "chroma-backup")
uv run python scripts/backup_restore.py restore --bundle (Join-Path $DrillRoot "chroma-backup") --target (Join-Path $DrillRoot "chroma-restored")
uv run python scripts/backup_restore.py verify --bundle (Join-Path $DrillRoot "chroma-backup") --target (Join-Path $DrillRoot "chroma-restored")
```

演练后检查每条命令输出的对象类型、`content_sha256` 和路径，并将命令、退出码、manifest 摘要及隔离 fixture 声明写入证据记录。清理由演练负责人确认 `$DrillRoot` 的解析绝对路径确属临时目录后单独执行，不纳入工具自动行为。

## 恢复判定与限制

成功判定为：三类对象均能创建 bundle、校验 bundle、恢复到不存在的新目标，并对恢复结果再次逐项校验；篡改、额外文件、符号链接、路径穿越与目标冲突均被拒绝。

此演练不能证明真实 MySQL 的事务一致快照、binlog/PITR、账号权限、真实 Chroma 版本兼容、运行中 Storage 写入冻结、三类对象的一致 generation 或批准的 RPO/RTO。在相应隔离拓扑和负责人批准前，AR-0 必须保持未通过。
