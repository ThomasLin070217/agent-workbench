# SharedNet MCP

使用固定版本 `@modelcontextprotocol/sdk` 1.32.2；`npm ci` 安装，`npm start` 独立启动。建议由 `../start-brain.sh` 统一管理。

地址为 `http://127.0.0.1:3002/mcp`，`MCP_PORT` 可覆盖。`GET /health` 返回服务标识与管理实例标识，管理器用它验证启动结果。

- `room_say({message, seat?})`：发送消息；精确 `@codex` 等 mention 唤醒 worker。
- `room_read({count?, seat?})`：读取最新消息，默认 20，范围 1–200。
- 配置 `SHAREDNET_SEAT` 时固定为该席位，禁止参数冒用其他席位。启动脚本始终设置独立 brain seat。
- `SHAREDNET_CWD` 指向管理器隔离的 Room 工作目录；手工启动时默认为项目目录。
- `SHAREDNET_BIN`、`SHAREDNET_BASE_URL`、`SHAREDNET_API_KEY`、`XDG_STATE_HOME`、`XDG_CONFIG_HOME` 由启动器传入。手工启动需使用相同 generation 下的配置与 local env；不要使用旧 seat 示例。
- `MCP_ALLOWED_ORIGINS` 是逗号分隔的浏览器 Origin 允许列表，默认空；无 Origin 的服务端请求不受此项限制。
- CLI 使用 argv 数组，无 shell；30 秒超时，输出合计最多 2 MiB。错误作为 `isError:true` 返回。

## 会话与重启

每个 POST 新建 Server 与 StreamableHTTPServerTransport，`sessionIdGenerator: undefined`，`enableJsonResponse: true`。这是无会话模式，不签发或维护 `Mcp-Session-Id`，GET/DELETE `/mcp` 返回 405。重启后无需恢复服务端 session；添加内存 session 会引入重启失效问题。

测试覆盖 initialize、tools/list、独立 brain 读写、参数拒绝、MCP 单独重启及附带旧 session header 的继续调用。ChatGPT 的 “Session terminated” 仍需结合客户端、ngrok 和当时日志诊断；此次没有重连线上 ChatGPT，不能宣称该提示已解决。隧道 URL 改变时要更新客户端配置。

参考：[SDK 无会话说明](https://ts.sdk.modelcontextprotocol.io/v2/api/%40modelcontextprotocol/node/streamableHttp.html)、本地已安装的 1.32.2 SDK 源码。`smoke-results.json` 是原有历史记录，不代表本次测试结果。

## 入口访问风险

当前没有 OAuth 或公网调用方认证。Origin 校验不是鉴权；持有隧道地址的调用方可读 Room 和发送 worker 指令。`SHAREDNET_API_KEY` 仅是后端凭据。需要公开使用时，应配置与客户端兼容的入口鉴权；本地测试可用 `START_NGROK=0`。此次没有修改演示中的 ngrok，也没有创建测试公网隧道。
