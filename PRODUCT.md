# SharedNet 工作台

## Platform
web

## Stack
现有 Python 标准库服务 + 原生 HTML/CSS/JavaScript，无需构建。

## Users and purpose
Thomas 从项目 GUI 查看 SharedNet Room 协作消息，找到任务对应的 Codex 与 DeepSeek 本地桌面客户端的原生会话，在原生应用继续聊天。Claude 暂不纳入。

## Confirmed constraints
沿用 Room 消息源；保留原生会话 ID，不创建替代会话。不假装已执行/已完成。参考 ChatGPT、DeepSeek 的侧栏与聊天交互。已安装回原项目；用户确认两个桌面客户端均可打开原会话。DeepSeek 不使用浏览器 Web UI。
