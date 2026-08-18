# 工作包 2：聊天 Markdown 安全渲染

日期：2026-08-17
状态：已完成（最终复核：2026-08-18）
关联记录：同目录 `change-log.md`、`test-record.md`

## 目标

消除聊天消息对原始 HTML 的信任渲染，确保历史消息、流式生成消息和重新生成消息共用同一套 Markdown 渲染规则，并限制链接协议。

## 实施范围

- 删除 `rehypeRaw`，让 `react-markdown` 将原始 HTML 按文本处理。
- 提取 `ChatMarkdown` 组件，作为 AI 聊天助手消息的唯一 Markdown 渲染入口。
- 保留代码高亮，并将链接限制为 `http(s)`、`mailto`、`tel`、根相对路径和锚点链接。
- 覆盖正常 Markdown、`script`、事件属性、`iframe`、`javascript:`、`data:` 和 `vbscript:` 输入。

## 回滚方式

恢复 `front/src/pages/AIChat.tsx` 的原渲染实现、移除新增聊天组件和测试，并恢复 `rehype-raw` 依赖及锁文件。回滚后会重新引入原始 HTML 渲染风险，除非同时引入并验证最小白名单 sanitizer。
