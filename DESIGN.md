---
name: SharedNet 工作台
description: 熟悉的聊天界面，衔接 Room 协作与原生桌面会话
colors:
  "bg": "#fff"
  "side": "#f6f7f5"
  "ink": "#202622"
  "muted": "#626b64"
  "line": "#e0e5df"
  "accent": "#216648"
  "tint": "#e9f0eb"
  "selected-ink": "#17492f"
  "session-hover": "#edf0eb"
  "accent-hover": "#174c35"
  "detail-surface": "#fafbf9"
  "code-surface": "#fbfcfa"
  "composer-border": "#d0d7cf"
  "warning": "#875022"
  "error": "#a03c28"
typography:
  headline:
    fontFamily: "-apple-system, BlinkMacSystemFont, \"Segoe UI\", \"PingFang SC\", sans-serif"
    fontSize: "22px"
    fontWeight: 550
    letterSpacing: "-0.02em"
  title:
    fontFamily: "-apple-system, BlinkMacSystemFont, \"Segoe UI\", \"PingFang SC\", sans-serif"
    fontSize: "17px"
    fontWeight: 600
  body:
    fontFamily: "-apple-system, BlinkMacSystemFont, \"Segoe UI\", \"PingFang SC\", sans-serif"
    fontSize: "14px"
    lineHeight: 1.85
  label:
    fontFamily: "-apple-system, BlinkMacSystemFont, \"Segoe UI\", \"PingFang SC\", sans-serif"
    fontSize: "12px"
  code:
    fontFamily: "ui-monospace, SFMono-Regular, monospace"
    fontSize: "12px"
rounded:
  "inline": "4px"
  "copy": "6px"
  "field": "8px"
  "navigation": "9px"
  "code": "10px"
  "composer": "16px"
  "pill": "20px"
spacing:
  "4": "4px"
  "8": "8px"
  "12": "12px"
  "16": "16px"
  "24": "24px"
  "32": "32px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.bg}"
    rounded: "{rounded.navigation}"
    padding: "12px 16px"
  button-primary-hover:
    backgroundColor: "{colors.accent-hover}"
  button-icon:
    textColor: "{colors.muted}"
    rounded: "{rounded.field}"
    width: "36px"
    height: "36px"
  button-copy:
    backgroundColor: "{colors.bg}"
    rounded: "{rounded.copy}"
    padding: "5px 8px"
  button-send:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.bg}"
    rounded: "{rounded.code}"
    width: "36px"
    height: "36px"
  search:
    backgroundColor: "{colors.bg}"
    textColor: "{colors.ink}"
    rounded: "{rounded.field}"
    padding: "10px 12px"
  navigation-selected:
    backgroundColor: "{colors.tint}"
    textColor: "{colors.selected-ink}"
    rounded: "{rounded.navigation}"
    padding: "14px 12px"
  composer:
    backgroundColor: "{colors.bg}"
    rounded: "{rounded.composer}"
  user-message:
    backgroundColor: "{colors.side}"
    rounded: "{rounded.composer}"
    padding: "14px 18px"
---

# Design System: SharedNet 工作台

## Overview

**Creative North Star: "熟悉的聊天工作台"**

沿用用户已选择的 ChatGPT / DeepSeek 聊天范式：白色阅读面、浅灰侧栏、系统字体和克制的墨绿色操作。视觉重心是可读的对话与可辨认的会话索引，保持原生桌面应用之间的连续感。

界面以轻边框和浅色表面区分层级。按钮与输入框柔和、直接，主要操作明显，辅助状态安静但可读。

**Key Characteristics:**

- 系统字体与清晰的中文阅读层级。
- 白色消息区、浅灰导航、墨绿色主要操作。
- 固定侧栏与底部输入区；移动端收起导航。

## Colors

墨绿色提供操作方向，略带绿调的中性色构成安静的阅读环境。以上前置 token 是规范值，与当前 style.css 对齐。

### Primary

- **墨绿（accent）**：原生应用入口、发送按钮、链接、焦点和连接圆点。
- **深墨绿（accent-hover）**：原生入口悬停；浅绿（tint）与深绿文字（selected-ink）标识当前导航。

### Neutral

- **白色阅读面（bg）**：正文与输入区域；浅灰侧栏（side）也用于用户气泡、选择器与代码标题。
- **深灰正文（ink）**与**次级灰（muted）**：区分正文、时间、会话 ID 和辅助说明。
- **柔灰边界（line / composer-border）**：细分导航、头部、代码块与输入区。
- **浅色辅助面（detail-surface / code-surface）**：原生会话详情和代码正文；session-hover 用于会话悬停。
- **棕色提示（warning）**与**红色错误（error）**：提示和连接失败，始终同时提供文字。

## Typography

使用前置 token 中的系统字体栈，不加载展示字体。正文采用舒展行高，元信息缩小但不代替正文。

- 空状态标题使用 headline；移动端缩至 19px。品牌为 19px。
- 页标题使用 title；原生会话详情标题为 16px。
- 消息使用 body；会话标题为 14px、550 字重、1.5 行高。
- 辅助标签使用 label；消息时间和 ID 多为 11px，发送说明为 10px。
- 代码使用 code；保留代码块的横向滚动。

## Layout

桌面占满视口（100dvh）。侧栏宽 272px，内边距 24px 16px 12px；会话索引独立滚动。右侧采用纵向布局：头部、可选会话详情、可滚动 Room 消息、底部输入区。头部最小高度 88px，内边距 20px 32px。

消息区围绕 760px 阅读宽度居中，横向至少留 24px。输入区外框最大宽度 808px，桌面横向内边距 24px。消息之间留 28px；发起人气泡左侧缩进 12%。

在视口宽度不超过 700px 时，导航成为宽 280px 的左侧抽屉。菜单按钮打开，关闭按钮、Escape 或选择会话关闭。头部最小高度 78px、内边距 16px；消息内边距 24px 18px，输入区 10px 12px。会话详情纵向排列，发起人气泡缩进减为 5%，隐藏键盘发送提示以留出输入空间。

## Elevation & Depth

默认用表面色与细边框建立层级。仅输入框使用轻微阴影（0 4px 14px #18231b05），打开的移动侧栏使用结构性阴影（12px 0 40px #18231b22）。不要将普通消息或会话列表改成悬浮卡片。

## Shapes

圆角遵循前置 rounded token：输入和用户气泡最柔和，导航与按钮适中，代码与复制控件更紧凑。常规边框为 1px。状态圆点直径 7px、完全圆形；图标为 22px 线条 SVG，描边宽度 1.7。

## Components

### Buttons

原生入口为墨绿实心按钮，悬停加深。发送按钮为 36px 方形图标按钮；刷新与关闭为透明图标按钮，悬停显示浅灰底。复制 ID 使用白底细边框。禁用按钮透明度减至 0.5，并显示不可用光标。

所有交互控件的键盘焦点为 2px accent 描边，偏移 3px；文本输入区偏移 -3px。按钮和链接的背景转换为 0.15s ease-out。移动抽屉滑动为 0.2s ease-out；prefers-reduced-motion 关闭转换和流畅滚动。

### Navigation

Room 入口与原生会话共用浅绿选中表面。会话项展示任务标题、Agent、状态和截断的 ID；标题允许换行。搜索框支持任务或会话过滤。连接状态同时展示文字，不能仅靠圆点。

### Inputs / Fields

搜索框为白底细边框。组合输入区使用 16px 圆角、轻阴影和独立操作行；文本区为 14px、1.6 行高，最大高度 180px。Agent 选择器为浅灰底，当前选项是整个 Room、Codex、DeepSeek。Enter 发送，Shift + Enter 换行；输入法组合期间不发送。失败保留草稿。

### Conversation

Agent 消息平铺在白色阅读面，发起人消息使用浅灰圆角气泡。元信息展示发送者、时间和序号。正文支持转义后的 Markdown 子集，代码块带复制入口。

首次展示最近 12 条 Room 消息；“查看更早的 Room 消息”每次增加 20 条。超过 600 字符的正文默认展示前 160 字符与展开入口，完整内容保留在折叠区。用户正在阅读上方时保留阅读位置并显示新消息按钮。

### Native session handoff

选择会话后，头部下方展示继续对话入口、原生 ID 和复制按钮；下方始终是 Room 协作消息。入口打开已有 Codex 或 DeepSeek 桌面会话。不可用或定位失败时在相邻位置说明原因；送达 Room、等待回复和桌面会话确认是不同状态。

## Do's and Don'ts

### Do:

- Do 保持 ChatGPT / DeepSeek 风格的侧栏、消息阅读区和底部输入区。
- Do 用文字说明状态与失败原因，保留键盘可见焦点。
- Do 让长正文和会话 ID 换行，代码块独立横向滚动。
- Do 将原生会话入口与对应 ID 放在一起，明确下方仍为 Room 消息。

### Don't:

- Don't 将 Room 送达状态表现成 Agent 已执行或已完成。
- Don't 在当前 Agent 选择器中加入 Claude；当前范围是 Room、Codex 和 DeepSeek。
- Don't 用装饰性大标题、指标卡片或强阴影取代熟悉的聊天布局。
