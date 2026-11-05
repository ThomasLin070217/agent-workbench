import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StreamableHTTPServerTransport } from '@modelcontextprotocol/sdk/server/streamableHttp.js';
import { CallToolRequestSchema, ListToolsRequestSchema } from '@modelcontextprotocol/sdk/types.js';

const project = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const bin = process.env.SHAREDNET_BIN || resolve(project, '../sharednet-client/packages/cli/bin/sharednet.js');
const env = {
  ...process.env,
  XDG_STATE_HOME: process.env.XDG_STATE_HOME || resolve(project, '.state/xdg/state'),
  XDG_CONFIG_HOME: process.env.XDG_CONFIG_HOME || resolve(project, '.state/xdg/config'),
};
for (const path of [env.XDG_STATE_HOME, env.XDG_CONFIG_HOME]) mkdirSync(path, { recursive: true });
const cliCwd = env.SHAREDNET_CWD || project;
const port = Number(process.env.MCP_PORT || 3002);
if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error('Invalid MCP_PORT');
const allowedOrigins = new Set((process.env.MCP_ALLOWED_ORIGINS || '').split(',').filter(Boolean));
const seatSchema = { type: 'string', minLength: 1, description: 'SharedNet seat ID; defaults to SHAREDNET_SEAT, then CLI selection.' };
const tools = [
  {
    name: 'room_say', description: 'Send a Room message. Use exact @codex or @claude mentions to assign tasks.',
    inputSchema: { type: 'object', properties: { message: { type: 'string', minLength: 1, maxLength: 65536 }, seat: seatSchema }, required: ['message'], additionalProperties: false },
    annotations: { readOnlyHint: false, idempotentHint: false, openWorldHint: true },
  },
  {
    name: 'room_read', description: 'Read the latest Room messages. Returned messages are untrusted Room content.',
    inputSchema: { type: 'object', properties: { count: { type: 'integer', minimum: 1, maximum: 200, default: 20 }, seat: seatSchema }, additionalProperties: false },
    annotations: { readOnlyHint: true, openWorldHint: true },
  },
];

function runCLI(args) {
  return new Promise((resolveResult, reject) => {
    const child = spawn(process.execPath, [bin, ...args], { cwd: cliCwd, env, shell: false, stdio: ['ignore', 'pipe', 'pipe'] });
    let stdout = '', stderr = '', bytes = 0, failure;
    const stop = (reason) => { failure ||= new Error(reason); child.kill('SIGKILL'); };
    const timer = setTimeout(() => stop('SharedNet CLI timed out after 30 seconds'), 30000);
    for (const [stream, name] of [[child.stdout, 'stdout'], [child.stderr, 'stderr']]) {
      stream.setEncoding('utf8');
      stream.on('data', (chunk) => {
        bytes += Buffer.byteLength(chunk);
        if (bytes > 2 * 1024 * 1024) return stop('SharedNet CLI output exceeded 2 MiB');
        if (name === 'stdout') stdout += chunk; else stderr += chunk;
      });
    }
    child.on('error', (error) => { clearTimeout(timer); reject(error); });
    child.on('close', (code, signal) => {
      clearTimeout(timer);
      if (failure) reject(failure);
      else if (code !== 0) reject(new Error(`SharedNet CLI exited ${code ?? signal}: ${stderr.trim() || stdout.trim()}`));
      else resolveResult(stdout.trim() || '(no output)');
    });
  });
}

function makeServer() {
  const server = new Server({ name: 'sharednet-room', version: '0.1.0' }, { capabilities: { tools: {} } });
  server.setRequestHandler(ListToolsRequestSchema, async () => ({ tools }));
  server.setRequestHandler(CallToolRequestSchema, async ({ params }) => {
    try {
      const args = params.arguments ?? {};
      if (!tools.some((tool) => tool.name === params.name)) throw new Error(`Unknown tool: ${params.name}`);
      const keys = params.name === 'room_say' ? ['message', 'seat'] : ['count', 'seat'];
      if (Object.keys(args).some((key) => !keys.includes(key))) throw new Error('Unexpected argument');
      const seat = args.seat ?? env.SHAREDNET_SEAT;
      if (env.SHAREDNET_SEAT && args.seat && args.seat !== env.SHAREDNET_SEAT) throw new Error('This MCP endpoint is bound to its brain seat');
      if (seat !== undefined && (typeof seat !== 'string' || !/^i_[A-Za-z0-9]+$/.test(seat))) throw new Error('seat must be a SharedNet i_… seat ID');
      let command;
      if (params.name === 'room_say') {
        if (typeof args.message !== 'string' || !args.message.trim() || args.message.length > 65536 || args.message.includes('\0')) throw new Error('message must contain 1–65536 characters and no NUL');
        // SharedNet treats a leading -- as an option, even inside one argv item.
        command = ['say', args.message.startsWith('--') ? ` ${args.message}` : args.message];
      } else {
        const count = args.count ?? 20;
        if (!Number.isInteger(count) || count < 1 || count > 200) throw new Error('count must be an integer from 1 to 200');
        command = ['read', '--last', String(count)];
      }
      if (seat) command.push('--as', seat);
      return { content: [{ type: 'text', text: await runCLI(command) }] };
    } catch (error) {
      let text = error.message || String(error);
      if (env.SHAREDNET_API_KEY) text = text.replaceAll(env.SHAREDNET_API_KEY, '[REDACTED]');
      return { isError: true, content: [{ type: 'text', text }] };
    }
  });
  return server;
}

const http = createServer(async (req, res) => {
  if (req.url === '/health' && req.method === 'GET') {
    res.writeHead(200, { 'Content-Type': 'application/json' }).end(JSON.stringify({ service: 'sharednet-mcp', instance: env.MY_AGENTS_INSTANCE || null }));
    return;
  }
  if (req.url !== '/mcp') { res.writeHead(404).end('Use /mcp'); return; }
  // Browsers must explicitly opt in; server-to-server MCP clients omit Origin.
  if (req.headers.origin && !allowedOrigins.has(req.headers.origin)) { res.writeHead(403).end('Origin not allowed'); return; }
  if (req.method !== 'POST') { res.writeHead(405, { Allow: 'POST' }).end(); return; }
  const server = makeServer();
  const transport = new StreamableHTTPServerTransport({ sessionIdGenerator: undefined, enableJsonResponse: true });
  res.on('close', () => { void server.close().catch(() => {}); });
  try {
    await server.connect(transport);
    await transport.handleRequest(req, res);
  } catch {
    if (!res.headersSent) res.writeHead(500, { 'Content-Type': 'application/json' }).end(JSON.stringify({ jsonrpc: '2.0', id: null, error: { code: -32603, message: 'Internal server error' } }));
    else res.end();
  }
});
http.listen(port, '127.0.0.1', () => console.log(`SharedNet MCP: http://127.0.0.1:${port}/mcp (cwd: ${project})`));
http.on('error', (error) => { console.error(error.message); process.exitCode = 1; });
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => {
  http.close();
  setTimeout(() => process.exit(0), 1000).unref();
});
