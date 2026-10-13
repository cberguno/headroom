import type { Limits } from "./config.js";
import type { Block, Message, Model, Tool, ToolCallBlock, ToolResultBlock } from "./types.js";

export type RunStopReason =
  | "finished" // the model answered without requesting tools
  | "turn_limit"
  | "token_limit"
  | "depth_limit"
  | "output_truncated" // the model hit its output cap with nothing left to do
  | "error"; // the model call failed

export interface RunOptions {
  model: Model;
  tools: Tool[];
  limits: Limits;
  workspace: string;
  /** Prior conversation (e.g. loaded from history) to continue from. */
  messages?: Message[];
  /** New user input appended before the first model call. */
  input?: string;
  system?: string;
  /** Nesting depth of this agent; 0 for the top-level agent. */
  depth?: number;
  /** Called for every message added to the conversation (use it to persist history). */
  onMessage?: (m: Message) => void | Promise<void>;
  onText?: (text: string) => void;
  onToolCall?: (call: ToolCallBlock) => void;
  onToolResult?: (result: ToolResultBlock, call: ToolCallBlock) => void;
}

export interface RunResult {
  stopReason: RunStopReason;
  messages: Message[];
  turns: number;
  usage: { inputTokens: number; outputTokens: number };
  finalText: string;
  error?: string;
}

export async function runAgent(opts: RunOptions): Promise<RunResult> {
  const messages: Message[] = [...(opts.messages ?? [])];
  const usage = { inputTokens: 0, outputTokens: 0 };
  let turns = 0;
  let finalText = "";
  const toolSpecs = opts.tools.map(({ name, description, inputSchema }) => ({ name, description, inputSchema }));
  const byName = new Map(opts.tools.map((t) => [t.name, t]));

  const add = async (m: Message) => {
    messages.push(m);
    await opts.onMessage?.(m);
  };
  const result = (stopReason: RunStopReason, error?: string): RunResult => ({
    stopReason, messages, turns, usage, finalText, ...(error ? { error } : {}),
  });

  if ((opts.depth ?? 0) > opts.limits.maxDepth) return result("depth_limit");
  if (opts.input !== undefined) await add({ role: "user", content: [{ type: "text", text: opts.input }] });

  for (;;) {
    // Limits are checked only between turns, so history never ends mid tool exchange.
    if (turns >= opts.limits.maxTurns) return result("turn_limit");
    if (usage.inputTokens + usage.outputTokens >= opts.limits.maxTotalTokens) return result("token_limit");
    turns++;

    const content: Block[] = [];
    const calls: ToolCallBlock[] = [];
    let truncated = false;
    try {
      for await (const ev of opts.model.complete(messages, toolSpecs, { system: opts.system })) {
        if (ev.type === "text") {
          const last = content[content.length - 1];
          if (last?.type === "text") last.text += ev.text;
          else content.push({ type: "text", text: ev.text });
          opts.onText?.(ev.text);
        } else if (ev.type === "tool_call") {
          const call: ToolCallBlock = { type: "tool_call", id: ev.id, name: ev.name, input: ev.input };
          content.push(call);
          calls.push(call);
          opts.onToolCall?.(call);
        } else if (ev.type === "usage") {
          usage.inputTokens += ev.inputTokens;
          usage.outputTokens += ev.outputTokens;
        } else if (ev.type === "done") {
          truncated = ev.stopReason === "max_tokens";
        }
      }
    } catch (e) {
      return result("error", e instanceof Error ? e.message : String(e));
    }

    if (content.length) await add({ role: "assistant", content });
    const text = content.filter((b) => b.type === "text").map((b) => b.text).join("");
    if (text) finalText = text;

    if (calls.length === 0) return result(truncated ? "output_truncated" : "finished");

    const results: ToolResultBlock[] = [];
    for (const call of calls) {
      const tool = byName.get(call.name);
      let res: ToolResultBlock;
      if (!tool) {
        res = { type: "tool_result", callId: call.id, content: `unknown tool: ${call.name}`, isError: true };
      } else {
        try {
          res = { type: "tool_result", callId: call.id, content: await tool.run(call.input, { workspace: opts.workspace }) };
        } catch (e) {
          res = { type: "tool_result", callId: call.id, content: e instanceof Error ? e.message : String(e), isError: true };
        }
      }
      results.push(res);
      opts.onToolResult?.(res, call);
    }
    await add({ role: "user", content: results });
  }
}
