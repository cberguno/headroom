import fs from "node:fs/promises";
import { loadConfig } from "./config.js";
import { HistoryStore } from "./history.js";
import { runAgent } from "./loop.js";
import { createModel } from "./model/index.js";
import { defaultTools } from "./tools/index.js";

const SYSTEM = "You are a capable agent. Use the tools when needed and stop when the task is done. Files live in the workspace folder, which is /workspace inside the shell tool.";

function parseArgs(argv: string[]) {
  const out: { prompt: string[]; resume?: string; id?: string; list: boolean } = { prompt: [], list: false };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i]!;
    if (a === "--resume") out.resume = argv[++i];
    else if (a === "--id") out.id = argv[++i];
    else if (a === "--list") out.list = true;
    else out.prompt.push(a);
  }
  return out;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const cfg = loadConfig();
  const history = new HistoryStore(cfg.historyDir);

  if (args.list) {
    console.log((await history.list()).join("\n") || "(no saved conversations)");
    return;
  }
  const input = args.prompt.join(" ").trim();
  if (!input) {
    console.error('usage: npm start -- [--resume <id>] [--id <name>] "your prompt"\n       npm start -- --list');
    process.exit(2);
  }

  const id = args.resume ?? args.id ?? new Date().toISOString().replace(/[:.]/g, "-");
  const prior = args.resume ? await history.load(args.resume) : [];
  await fs.mkdir(cfg.workspace, { recursive: true });

  const res = await runAgent({
    model: createModel(cfg),
    tools: defaultTools(cfg),
    limits: cfg.limits,
    workspace: cfg.workspace,
    messages: prior,
    input,
    system: SYSTEM,
    onMessage: (m) => history.append(id, m),
    onText: (t) => process.stdout.write(t),
    onToolCall: (c) => console.error(`\n[tool] ${c.name} ${JSON.stringify(c.input)}`),
    onToolResult: (r) => console.error(`[result${r.isError ? " (error)" : ""}] ${r.content.slice(0, 200)}`),
  });

  console.error(
    `\n\nstop: ${res.stopReason}${res.error ? ` (${res.error})` : ""} | turns: ${res.turns} | tokens: ${res.usage.inputTokens} in / ${res.usage.outputTokens} out | conversation: ${id}`,
  );
  if (res.stopReason === "error") process.exit(1);
}

main().catch((e) => {
  console.error(e instanceof Error ? e.message : e);
  process.exit(1);
});
