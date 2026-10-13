import type { Config } from "../config.js";
import type { Block, CompleteOptions, Message, Model, ModelEvent, StopReason, ToolSpec } from "../types.js";

type FetchLike = typeof fetch;

export function toOpenAIMessages(messages: Message[], system?: string) {
  const out: Array<Record<string, unknown>> = [];
  if (system) out.push({ role: "system", content: system });
  for (const m of messages) {
    if (m.role === "assistant") {
      const text = m.content.filter((b): b is Extract<Block, { type: "text" }> => b.type === "text");
      const calls = m.content.filter((b): b is Extract<Block, { type: "tool_call" }> => b.type === "tool_call");
      const msg: Record<string, unknown> = { role: "assistant", content: text.map((t) => t.text).join("") || null };
      if (calls.length) {
        msg.tool_calls = calls.map((c) => ({
          id: c.id,
          type: "function",
          function: { name: c.name, arguments: JSON.stringify(c.input) },
        }));
      }
      out.push(msg);
    } else {
      for (const b of m.content) {
        if (b.type === "tool_result") out.push({ role: "tool", tool_call_id: b.callId, content: b.content });
        else if (b.type === "text") out.push({ role: "user", content: b.text });
      }
    }
  }
  return out;
}

export function createOpenAIModel(cfg: Config, fetchImpl: FetchLike = fetch): Model {
  return {
    async *complete(messages: Message[], tools: ToolSpec[], options?: CompleteOptions): AsyncIterable<ModelEvent> {
      const body: Record<string, unknown> = {
        model: cfg.model,
        max_tokens: cfg.maxOutputTokens,
        messages: toOpenAIMessages(messages, options?.system),
      };
      if (tools.length) {
        body.tools = tools.map((t) => ({
          type: "function",
          function: { name: t.name, description: t.description, parameters: t.inputSchema },
        }));
      }
      const headers: Record<string, string> = { "content-type": "application/json" };
      if (cfg.apiKey) headers.authorization = `Bearer ${cfg.apiKey}`;
      const res = await fetchImpl(`${cfg.baseUrl}/chat/completions`, {
        method: "POST",
        headers,
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(`OpenAI-compatible API ${res.status}: ${(await res.text()).slice(0, 500)}`);
      const data = (await res.json()) as {
        choices: Array<{
          finish_reason: string;
          message: {
            content?: string | null;
            tool_calls?: Array<{ id: string; function: { name: string; arguments: string } }>;
          };
        }>;
        usage?: { prompt_tokens?: number; completion_tokens?: number };
      };
      const choice = data.choices[0];
      if (!choice) throw new Error("OpenAI-compatible API returned no choices");
      if (choice.message.content) yield { type: "text", text: choice.message.content };
      for (const c of choice.message.tool_calls ?? []) {
        let input: Record<string, unknown> = {};
        try {
          input = JSON.parse(c.function.arguments || "{}");
        } catch {
          input = { _raw: c.function.arguments };
        }
        yield { type: "tool_call", id: c.id, name: c.function.name, input };
      }
      yield {
        type: "usage",
        inputTokens: data.usage?.prompt_tokens ?? 0,
        outputTokens: data.usage?.completion_tokens ?? 0,
      };
      const stop: StopReason =
        choice.message.tool_calls?.length ? "tool_use" : choice.finish_reason === "length" ? "max_tokens" : "end";
      yield { type: "done", stopReason: stop };
    },
  };
}
