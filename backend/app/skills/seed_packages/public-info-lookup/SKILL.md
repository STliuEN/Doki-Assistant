---
name: public-info-lookup
description: "查询中国大学公开资料；对公网域名或公网 IP 做 ping 和端口连通检测。"
---
# 外部信息查询

用于通过外部 MCP 工具查询公开信息和做轻量网络连通性检测。

- 用户询问中国大学的建校时间、地址、面积、简介、学科等公开资料时，调用 `mcp_public_info_lookup_query_university_info_tool`。
- 查询大学信息时，`daxue` 使用尽量准确的中文校名，例如 `武汉大学`、`清华大学`。
- 用户要求检测公共域名或公网 IP 的 ping、端口连通、延迟时，调用 `mcp_public_info_lookup_ping_check_tool`。
- PING 检测默认 `port=80`、`timeout=10`、`lang=zh-cn`；用户给出端口或超时时按用户要求填写。
- 不要用 PING 工具检测 localhost、内网 IP、保留地址或项目内部服务。
- 外部 API 返回异常、结果为空或字段缺失时，如实说明，不要补编学校信息或网络状态。
- 回答时简洁总结关键字段，并说明信息来自外部公开 API，可能需要以学校官网或权威网络监测为准。
