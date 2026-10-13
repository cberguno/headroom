import fs from "node:fs/promises";
import path from "node:path";
import type { Tool } from "../types.js";

/** Resolve a user path inside the workspace; reject traversal and symlink escapes. */
export async function resolveInWorkspace(workspace: string, rel: unknown): Promise<string> {
  if (typeof rel !== "string" || !rel) throw new Error("path must be a non-empty string");
  const root = await fs.realpath(workspace);
  const target = path.resolve(root, rel);
  const inside = (p: string) => p === root || p.startsWith(root + path.sep);
  if (!inside(target)) throw new Error(`path escapes the workspace: ${rel}`);
  // Walk up to the deepest existing ancestor and check its real location.
  let probe = target;
  for (;;) {
    try {
      const real = await fs.realpath(probe);
      if (!inside(real)) throw new Error(`path escapes the workspace via symlink: ${rel}`);
      break;
    } catch (e) {
      if ((e as NodeJS.ErrnoException).code !== "ENOENT") throw e;
      const parent = path.dirname(probe);
      if (parent === probe) break;
      probe = parent;
    }
  }
  return target;
}

const MAX_READ = 200_000;

export const readFileTool: Tool = {
  name: "read_file",
  description: "Read a UTF-8 text file from the workspace folder.",
  inputSchema: {
    type: "object",
    properties: { path: { type: "string", description: "Path relative to the workspace" } },
    required: ["path"],
  },
  async run(input, ctx) {
    const file = await resolveInWorkspace(ctx.workspace, input.path);
    const text = await fs.readFile(file, "utf8");
    return text.length > MAX_READ ? `${text.slice(0, MAX_READ)}\n...[truncated ${text.length - MAX_READ} chars]` : text;
  },
};

export const writeFileTool: Tool = {
  name: "write_file",
  description: "Write (create or overwrite) a UTF-8 text file in the workspace folder. Parent directories are created.",
  inputSchema: {
    type: "object",
    properties: {
      path: { type: "string", description: "Path relative to the workspace" },
      content: { type: "string" },
    },
    required: ["path", "content"],
  },
  async run(input, ctx) {
    if (typeof input.content !== "string") throw new Error("content must be a string");
    const file = await resolveInWorkspace(ctx.workspace, input.path);
    await fs.mkdir(path.dirname(file), { recursive: true });
    await fs.writeFile(file, input.content, "utf8");
    return `wrote ${Buffer.byteLength(input.content)} bytes to ${String(input.path)}`;
  },
};
