import path from "node:path";

export interface Limits {
  maxDepth: number;
  maxTurns: number;
  maxTotalTokens: number;
}

export interface Config {
  provider: "anthropic" | "openai";
  model: string;
  maxOutputTokens: number;
  apiKey: string;
  baseUrl: string;
  limits: Limits;
  workspace: string;
  historyDir: string;
  shell: { image: string; timeoutMs: number; network: string };
}

function int(env: NodeJS.ProcessEnv, key: string, fallback: number): number {
  const raw = env[key];
  if (raw === undefined || raw === "") return fallback;
  const n = Number(raw);
  if (!Number.isInteger(n) || n <= 0) throw new Error(`${key} must be a positive integer, got "${raw}"`);
  return n;
}

export function loadConfig(env: NodeJS.ProcessEnv = process.env): Config {
  const provider = (env.MODEL_PROVIDER || "anthropic").toLowerCase();
  if (provider !== "anthropic" && provider !== "openai") {
    throw new Error(`MODEL_PROVIDER must be "anthropic" or "openai", got "${provider}"`);
  }
  const apiKey = (provider === "anthropic" ? env.ANTHROPIC_API_KEY : env.OPENAI_API_KEY) ?? "";
  const baseUrl =
    provider === "anthropic"
      ? env.ANTHROPIC_BASE_URL || "https://api.anthropic.com"
      : env.OPENAI_BASE_URL || "https://api.openai.com/v1";
  return {
    provider,
    model: env.MODEL_NAME || (provider === "anthropic" ? "claude-sonnet-5-5" : "gpt-4o"),
    maxOutputTokens: int(env, "MODEL_MAX_OUTPUT_TOKENS", 4096),
    apiKey,
    baseUrl: baseUrl.replace(/\/+$/, ""),
    limits: {
      maxDepth: int(env, "MAX_DEPTH", 3),
      maxTurns: int(env, "MAX_TURNS", 20),
      maxTotalTokens: int(env, "MAX_TOTAL_TOKENS", 200_000),
    },
    workspace: path.resolve(env.WORKSPACE_DIR || "./workspace"),
    historyDir: path.resolve(env.HISTORY_DIR || "./.history"),
    shell: {
      image: env.SHELL_IMAGE || "alpine:3.20",
      timeoutMs: int(env, "SHELL_TIMEOUT_MS", 30_000),
      network: env.SHELL_NETWORK || "none",
    },
  };
}
