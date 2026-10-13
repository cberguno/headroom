import type { Config } from "../config.js";
import type { Tool } from "../types.js";
import { fetchTool } from "./fetch.js";
import { readFileTool, writeFileTool } from "./files.js";
import { shellTool } from "./shell.js";

export function defaultTools(cfg: Config): Tool[] {
  return [shellTool(cfg.shell), readFileTool, writeFileTool, fetchTool()];
}
