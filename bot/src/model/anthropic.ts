import type { Config } from "../config.js";
import type { CompleteOptions, Message, Model, ModelEvent, StopReason, ToolSpec } from "../types.js";

type FetchLike = typeof fetch;

export function toAnthropicMessages(messages: Message[]) {
  return messages.map((m) => ({
    role: m.role,
    content: m.content.map((b) => {
      if (b.type === "text") return { type: "text", text: b.text };
      if (b.type === "tool_call") return { type: "tool_use", id: b.id, name: b.name, input: b.input };
      return { type: "tool_result", tool_use_id: b.callId, content: b.content, is_error: b.isError ?? false };
    }),
  }));
}

export function createAnthropicModel(cfg: Config, fetchImpl: FetchLike = fetch): Model {
  return {
    async *complete(messages: Message[], tools: ToolSpec[], options?: CompleteOptions): AsyncIterable<ModelEvent> {
      if (!cfg.apiKey) throw new Error("ANTHROPIC_API_KEY is not set");
      const body: Record<string, unknown> = {
        model: cfg.model,
        max_tokens: cfg.maxOutputTokens,
        messages: toAnthropicMessages(messages),
      };
      if (options?.system) body.system = options.system;
      if (tools.length) {
        body.tools = tools.map((t) => ({ name: t.name, description: t.description, input_schema: t.inputSchema }));
      }
      const res = await fetchImpl(`${cfg.baseUrl}/v1/messages`, {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-api-key": cfg.apiKey,
          "anthropic-version": "2023-06-01",
        },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(`Anthropic API ${res.status}: ${(await res.text()).slice(0, 500)}`);
      const data = (await res.json()) as {
        content: Array<{ type: string; text?: string; id?: string; name?: string; input?: Record<string, unknown> }>;
        stop_reason: string;
        usage?: { input_tokens?: number; output_tokens?: number };
      };
      for (const b of data.content) {
        if (b.type === "text" && b.text) yield { type: "text", text: b.text };
        else if (b.type === "tool_use") {
          yield { type: "tool_call", id: b.id!, name: b.name!, input: b.input ?? {} };
        }
      }
      yield {
        type: "usage",
        inputTokens: data.usage?.input_tokens ?? 0,
        outputTokens: data.usage?.output_tokens ?? 0,
      };
      const stop: StopReason =
        data.stop_reason === "tool_use" ? "tool_use" : data.stop_reason === "max_tokens" ? "max_tokens" : "end";
      yield { type: "done", stopReason: stop };
    },
  };
}
