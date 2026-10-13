import type { Config } from "../config.js";
import type { Model } from "../types.js";
import { createAnthropicModel } from "./anthropic.js";
import { createOpenAIModel } from "./openai.js";

export function createModel(cfg: Config): Model {
  return cfg.provider === "anthropic" ? createAnthropicModel(cfg) : createOpenAIModel(cfg);
}
