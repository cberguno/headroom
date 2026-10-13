import type { Limits } from "../src/config.js";
import type { ModelEvent, Tool } from "../src/types.js";

export const limits: Limits = { maxDepth: 2, maxTurns: 10, maxTotalTokens: 10_000 };

export const usage = (i = 10, o = 5): ModelEvent => ({ type: "usage", inputTokens: i, outputTokens: o });
export const say = (text: string): ModelEvent[] => [{ type: "text", text }, usage(), { type: "done", stopReason: "end" }];
export const call = (id: string, name: string, input: Record<string, unknown> = {}): ModelEvent[] => [
  { type: "tool_call", id, name, input }, usage(), { type: "done", stopReason: "tool_use" },
];

export const echoTool: Tool = {
  name: "echo",
  description: "echo",
  inputSchema: { type: "object", properties: { text: { type: "string" } } },
  async run(input) {
    return `echo:${String(input.text)}`;
  },
};
