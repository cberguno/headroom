export type TextBlock = { type: "text"; text: string };
export type ToolCallBlock = { type: "tool_call"; id: string; name: string; input: Record<string, unknown> };
export type ToolResultBlock = { type: "tool_result"; callId: string; content: string; isError?: boolean };
export type Block = TextBlock | ToolCallBlock | ToolResultBlock;

/** Tool results travel in "user" messages, as in the Anthropic API. */
export interface Message {
  role: "user" | "assistant";
  content: Block[];
}

export interface ToolContext {
  workspace: string;
}

export interface Tool {
  name: string;
  description: string;
  /** JSON Schema for the tool input. */
  inputSchema: Record<string, unknown>;
  run(input: Record<string, unknown>, ctx: ToolContext): Promise<string>;
}

export type ToolSpec = Pick<Tool, "name" | "description" | "inputSchema">;

export type StopReason = "end" | "tool_use" | "max_tokens";

export type ModelEvent =
  | { type: "text"; text: string }
  | { type: "tool_call"; id: string; name: string; input: Record<string, unknown> }
  | { type: "usage"; inputTokens: number; outputTokens: number }
  | { type: "done"; stopReason: StopReason };

export interface CompleteOptions {
  system?: string;
}

export interface Model {
  complete(messages: Message[], tools: ToolSpec[], options?: CompleteOptions): AsyncIterable<ModelEvent>;
}
