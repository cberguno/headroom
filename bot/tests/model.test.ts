import { describe, expect, it, vi } from "vitest";
import { loadConfig } from "../src/config.js";
import { createAnthropicModel } from "../src/model/anthropic.js";
import { createOpenAIModel } from "../src/model/openai.js";
import type { Message, ModelEvent } from "../src/types.js";

const json = (data: unknown, status = 200) => vi.fn(async () => new Response(JSON.stringify(data), { status })) as unknown as typeof fetch;
const collect = async (it: AsyncIterable<ModelEvent>) => { const o: ModelEvent[] = []; for await (const e of it) o.push(e); return o; };
const convo: Message[] = [
  { role: "user", content: [{ type: "text", text: "hi" }] },
  { role: "assistant", content: [{ type: "tool_call", id: "t1", name: "echo", input: { a: 1 } }] },
  { role: "user", content: [{ type: "tool_result", callId: "t1", content: "ok" }] },
];
const tools = [{ name: "echo", description: "d", inputSchema: { type: "object" } }];

describe("config", () => {
  it("applies defaults and reads env", () => {
    const c = loadConfig({});
    expect(c.provider).toBe("anthropic");
    expect(c.limits).toEqual({ maxDepth: 3, maxTurns: 20, maxTotalTokens: 200_000 });
    const c2 = loadConfig({ MODEL_PROVIDER: "openai", MODEL_NAME: "m", OPENAI_BASE_URL: "http://localhost:11434/v1/", MAX_TURNS: "5" });
    expect(c2.baseUrl).toBe("http://localhost:11434/v1");
    expect(c2.limits.maxTurns).toBe(5);
  });
  it("rejects bad values", () => {
    expect(() => loadConfig({ MODEL_PROVIDER: "x" })).toThrow(/MODEL_PROVIDER/);
    expect(() => loadConfig({ MAX_TURNS: "0" })).toThrow(/MAX_TURNS/);
  });
});

describe("anthropic model", () => {
  const cfg = loadConfig({ ANTHROPIC_API_KEY: "k", MODEL_NAME: "claude-test" });
  it("sends the right request and maps the response to events", async () => {
    const f = json({ content: [{ type: "text", text: "hey" }, { type: "tool_use", id: "t2", name: "echo", input: { b: 2 } }], stop_reason: "tool_use", usage: { input_tokens: 7, output_tokens: 3 } });
    const events = await collect(createAnthropicModel(cfg, f).complete(convo, tools, { system: "sys" }));
    expect(events).toEqual([
      { type: "text", text: "hey" },
      { type: "tool_call", id: "t2", name: "echo", input: { b: 2 } },
      { type: "usage", inputTokens: 7, outputTokens: 3 },
      { type: "done", stopReason: "tool_use" },
    ]);
    const [url, init] = vi.mocked(f).mock.calls[0]!;
    expect(url).toBe("https://api.anthropic.com/v1/messages");
    const body = JSON.parse((init as RequestInit).body as string);
    expect(body).toMatchObject({ model: "claude-test", system: "sys", tools: [{ name: "echo", input_schema: { type: "object" } }] });
    expect(body.messages[2].content[0]).toMatchObject({ type: "tool_result", tool_use_id: "t1" });
    expect(((init as RequestInit).headers as Record<string, string>)["x-api-key"]).toBe("k");
  });
  it("fails clearly without a key or on API errors", async () => {
    await expect(collect(createAnthropicModel(loadConfig({}), json({})).complete(convo, tools))).rejects.toThrow(/ANTHROPIC_API_KEY/);
    await expect(collect(createAnthropicModel(cfg, json({ error: "bad" }, 500)).complete(convo, tools))).rejects.toThrow(/500/);
  });
});

describe("openai-compatible model", () => {
  const cfg = loadConfig({ MODEL_PROVIDER: "openai", OPENAI_BASE_URL: "http://x/v1", MODEL_NAME: "m" });
  it("converts messages and maps tool calls back", async () => {
    const f = json({ choices: [{ finish_reason: "tool_calls", message: { content: null, tool_calls: [{ id: "c9", function: { name: "echo", arguments: '{"z":1}' } }] } }], usage: { prompt_tokens: 4, completion_tokens: 2 } });
    const events = await collect(createOpenAIModel(cfg, f).complete(convo, tools, { system: "sys" }));
    expect(events).toEqual([
      { type: "tool_call", id: "c9", name: "echo", input: { z: 1 } },
      { type: "usage", inputTokens: 4, outputTokens: 2 },
      { type: "done", stopReason: "tool_use" },
    ]);
    const body = JSON.parse((vi.mocked(f).mock.calls[0]![1] as RequestInit).body as string);
    expect(body.messages.map((m: { role: string }) => m.role)).toEqual(["system", "user", "assistant", "tool"]);
    expect(body.messages[2].tool_calls[0].function.arguments).toBe('{"a":1}');
    expect(body.messages[3]).toMatchObject({ tool_call_id: "t1", content: "ok" });
    expect(vi.mocked(f).mock.calls[0]![0]).toBe("http://x/v1/chat/completions");
  });
  it("maps plain text and length stops", async () => {
    const f = json({ choices: [{ finish_reason: "length", message: { content: "cut" } }] });
    const events = await collect(createOpenAIModel(cfg, f).complete(convo, []));
    expect(events.at(-1)).toEqual({ type: "done", stopReason: "max_tokens" });
  });
});
