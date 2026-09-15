# E8 变更日志

## 2026-09-15

- 完成 E8 最终门禁，final decision 标记为 closed。
- 确认 MySQL 为业务唯一权威，pending action 存 SQL。
- 确认 Chroma 为 SQL generation 驱动的可重建投影。
- 补齐三类业务 smoke 和六条 RAG 分支的真实证据。
- 完成 SQL schema/FK/digest/orphan 对账和 SQL→Chroma 对账。
- 完成 RPO/RTO：RPO 0，RTO 3.752 秒。
- 完成 reference audit；旧兼容路径保留但对 E8 业务 fail-closed。
- 保持 new-api observe-only，保持 MySQL 全局只读标志 0/0。
- 重写当前核心文档，消除历史状态对最终判定的覆盖。

## 后续范围

个人部署或生产化若有需要再另立项目；E-number 本身已完成架构精简与收口。
