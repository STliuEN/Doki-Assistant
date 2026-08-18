# 工作包 2 变更记录

日期：2026-08-17

- 新增 `front/src/features/chat/components/ChatMarkdown.tsx`，集中承载聊天助手消息的 Markdown 渲染。
- 新增 `front/src/features/chat/components/chatMarkdownSecurity.ts`，限制可导航链接协议；不安全协议统一改写为 `#`。
- 将 `AIChat` 的助手消息替换为 `ChatMarkdown`，因此历史加载、SSE 流式追加、确认操作和重新生成均使用相同渲染组件。
- 移除 `rehypeRaw` 的代码引用、`package.json` 直接依赖和锁文件中的专属依赖树。
- 新增 `ChatMarkdown.test.tsx`，验证 Markdown 正常语义保留，原始 `script`、事件属性和 `iframe` 不会被创建为 DOM 节点，并验证危险 URL 协议被阻止。

兼容性说明：标准 Markdown、代码高亮、HTTP(S) 链接、邮件链接、电话链接、根相对路径和锚点链接继续可用。原本依赖聊天消息中嵌入 HTML 的内容将以可见文本显示，这是有意的安全行为变更。
