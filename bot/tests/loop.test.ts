import { describe, expect, it } from "vitest";
import { runAgent } from "../src/loop.js";
import { createMockModel } from "../src/model/mock.js";
import type { Message, Tool } from "../src/types.js";
import { call, echoTool, limits, say, usage } from "./helpers.js";

const base = { tools: [echoTool], limits, workspace: "/tmp" };

describe("agent loop", () => {
  it("finishes immediately when the model answers without tools", async () => {
    const model = createMockModel([say("hello")]);
    const r = await runAgent({ ...base, model, input: "hi" });
    expect(r.stopReason).toBe("finished");
    expect(r.finalText).toBe("hello");
    expect(r.turns).toBe(1);
    expect(r.messages.map((m) => m.role)).toEqual(["user", "assistant"]);
  });

  it("calls tools until the model finishes, feeding results back", async () => {
    const model = createMockModel([call("c1", "echo", { text: "a" }), call("c2", "echo", { text: "b" }), say("done")]);
    const r = await runAgent({ ...base, model, input: "go" });
    expect(r.stopReason).toBe("finished");
    expect(r.turns).toBe(3);
    expect(r.usage).toEqual({ inputTokens: 30, outputTokens: 15 });
    const results = r.messages.flatMap((m) => m.content).filter((b) => b.type === "tool_result");
    expect(results).toEqual([
      { type: "tool_result", callId: "c1", content: "echo:a" },
      { type: "tool_result", callId: "c2", content: "echo:b" },
    ]);
    // the model saw the first tool result on its second call
    expect(JSON.stringify(model.calls[1]!.messages)).toContain("echo:a");
  });

  it("runs multiple tool calls from one turn and reports them in one user message", async () => {
    const model = createMockModel([
      [{ type: "tool_call", id: "x", name: "echo", input: { text: "1" } }, { type: "tool_call", id: "y", name: "echo", input: { text: "2" } }, usage(), { type: "done", stopReason: "tool_use" }],
      say("ok"),
    ]);
    const r = await runAgent({ ...base, model, input: "go" });
    const toolMsg = r.messages[2]!;
    expect(toolMsg.role).toBe("user");
    expect(toolMsg.content).toHaveLength(2);
  });

  it("returns tool errors and unknown tools to the model instead of crashing", async () => {
    const boom: Tool = { ...echoTool, name: "boom", run: async () => { throw new Error("kaput"); } };
    const model = createMockModel([call("1", "boom"), call("2", "nope"), say("recovered")]);
    const r = await runAgent({ ...base, tools: [boom], model, input: "go" });
    expect(r.stopReason).toBe("finished");
    const results = r.messages.flatMap((m) => m.content).filter((b) => b.type === "tool_result");
    expect(results).toMatchObject([
      { content: "kaput", isError: true },
      { content: "unknown tool: nope", isError: true },
    ]);
  });

  it("passes tool specs and system prompt to the model", async () => {
    const model = createMockModel([say("x")]);
    await runAgent({ ...base, model, input: "hi", system: "sys" });
    expect(model.calls[0]!.tools.map((t) => t.name)).toEqual(["echo"]);
  });

  it("reports model failures as stopReason=error", async () => {
    const model = { async *complete() { throw new Error("api down"); } };
    const r = await runAgent({ ...base, model, input: "hi" });
    expect(r.stopReason).toBe("error");
    expect(r.error).toBe("api down");
  });

  it("flags output truncation when the model stops on max_tokens without tools", async () => {
    const model = createMockModel([[{ type: "text", text: "partial" }, usage(), { type: "done", stopReason: "max_tokens" }]]);
    const r = await runAgent({ ...base, model, input: "hi" });
    expect(r.stopReason).toBe("output_truncated");
  });

  it("emits every message via onMessage and continues from prior history", async () => {
    const prior: Message[] = [
      { role: "user", content: [{ type: "text", text: "first" }] },
      { role: "assistant", content: [{ type: "text", text: "reply" }] },
    ];
    const seen: Message[] = [];
    const model = createMockModel([say("second reply")]);
    const r = await runAgent({ ...base, model, messages: prior, input: "second", onMessage: (m) => { seen.push(m); } });
    expect(seen.map((m) => m.role)).toEqual(["user", "assistant"]);
    expect(r.messages).toHaveLength(4);
    expect(JSON.stringify(model.calls[0]!.messages)).toContain("first");
  });
});

describe("limits", () => {
  const forever = () => createMockModel([call("c", "echo", { text: "again" })]);

  it("stops at the turn limit", async () => {
    const r = await runAgent({ ...base, model: forever(), limits: { ...limits, maxTurns: 3 }, input: "go" });
    expect(r.stopReason).toBe("turn_limit");
    expect(r.turns).toBe(3);
  });

  it("stops at the token limit", async () => {
    // each turn uses 15 tokens; limit 40 -> stops after the 3rd turn (45 >= 40)
    const r = await runAgent({ ...base, model: forever(), limits: { ...limits, maxTotalTokens: 40 }, input: "go" });
    expect(r.stopReason).toBe("token_limit");
    expect(r.turns).toBe(3);
  });

  it("stops at the depth limit without calling the model", async () => {
    const model = createMockModel([say("never")]);
    const r = await runAgent({ ...base, model, depth: 3, limits: { ...limits, maxDepth: 2 }, input: "go" });
    expect(r.stopReason).toBe("depth_limit");
    expect(model.calls).toHaveLength(0);
  });

  it("allows running exactly at the max depth", async () => {
    const r = await runAgent({ ...base, model: createMockModel([say("ok")]), depth: 2, input: "go" });
    expect(r.stopReason).toBe("finished");
  });

  it("leaves history resumable when a limit hits: every tool call has a result", async () => {
    const r = await runAgent({ ...base, model: forever(), limits: { ...limits, maxTurns: 2 }, input: "go" });
    expect(r.stopReason).toBe("turn_limit");
    const last = r.messages[r.messages.length - 1]!;
    expect(last.role).toBe("user");
    expect(last.content[0]!.type).toBe("tool_result");
    const calls = r.messages.flatMap((m) => m.content).filter((b) => b.type === "tool_call").length;
    const results = r.messages.flatMap((m) => m.content).filter((b) => b.type === "tool_result").length;
    expect(results).toBe(calls);
  });
});
