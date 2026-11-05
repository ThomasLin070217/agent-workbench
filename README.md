# Agent Workbench

A local project workbench built on [SharedNet](https://github.com/systemind-team/sharednet-client), with a ChatGPT-facing MCP bridge and links to existing Codex and local DeepSeek Harness conversations.

Independent integration project; not an official SharedNet distribution. SharedNet provides Rooms, messaging and wake delivery. This repository contains the application UI, local process management, adapters and desktop session bridge. It does not vendor or replace the SharedNet CLI.

## Status

Early working prototype, not a complete autonomous project orchestration system. Current features: local Room viewer, message submission with retry protection, native session indexing, Codex deep links, and a DeepSeek desktop-profile session selection plugin.

Task-specific session isolation is supported when the adapter receives an explicit `task_id`; ordinary Room command wakes do not yet supply that field. Codex defaults to read-only; explicit local task configuration can opt into `CODEX_TASK_SANDBOX=workspace-write`.

Not yet complete: live GUI/CLI turn coordination, automatic capture of human guidance, versioned cross-agent decisions, per-task worktree management, independent review/merge gates, and reliable end-to-end ChatGPT connectivity. A completed model turn is not a completed project task. No ChatGPT private conversation history is mirrored.

## Local setup

Requires macOS for the current desktop bridge, Python 3.10+, Node 22.18+, a compatible SharedNet CLI (local server available from 0.1.17), and separately installed/authenticated Codex and DeepSeek Harness.

1. Keep a SharedNet checkout alongside this directory as `sharednet-client`, or configure `SHAREDNET_BIN` explicitly for the runtime. The viewer also needs that variable when using a non-sibling checkout.
2. Run `npm ci --prefix mcp-server`.
3. Copy `agents.env.example` to `agents.env` and configure locally. Never commit credentials.
4. Run `./start-brain.sh`, then `./launch-workbench.sh`.
5. Open http://127.0.0.1:3003.
6. To enable local DeepSeek desktop selection, launch its desktop app once and run `python3 install-desktop-bridge.py`. The installer backs up and updates the Desktop profile's plugin patch.

The example disables the public tunnel. The current MCP endpoint has no caller authentication; do not expose it publicly as a production deployment. ChatGPT access needs a separately configured and secured reachable endpoint.

`./stop.sh` stops processes owned by the runtime manager. The separately launched viewer has a separate lifecycle. SharedNet's current local server is in-memory; its history does not survive a local-server restart.

## Verification

```sh
python3 -m unittest discover -s tests -v
node --check app.js
node --check mcp-server/server.mjs
```

Integration tests require the compatible SharedNet CLI and installed MCP dependencies. They use temporary directories, local ports and model stubs, not live model calls.

## Relationship with upstream

See [UPSTREAM.md](UPSTREAM.md) for boundaries and contribution candidates, and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for attribution. This repository is initially private while the integration is validated; no public launch or endorsement is implied.
