import type { Message, Model, ModelEvent, ToolSpec } from "../types.js";

/** A scripted model for tests: each call to complete() yields the next script entry. */
export function createMockModel(script: ModelEvent[][]): Model & { calls: Array<{ messages: Message[]; tools: ToolSpec[] }> } {
  const calls: Array<{ messages: Message[]; tools: ToolSpec[] }> = [];
  let i = 0;
  return {
    calls,
    async *complete(messages, tools) {
      calls.push({ messages: structuredClone(messages), tools });
      const events = script[Math.min(i++, script.length - 1)];
      if (!events) throw new Error("mock model has an empty script");
      for (const e of events) yield e;
    },
  };
}
