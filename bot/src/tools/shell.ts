import { execFile } from "node:child_process";
import type { Tool } from "../types.js";

export interface ExecResult {
  stdout: string;
  stderr: string;
  code: number | null;
  timedOut: boolean;
}
export type ExecFn = (file: string, args: string[], timeoutMs: number) => Promise<ExecResult>;

export const defaultExec: ExecFn = (file, args, timeoutMs) =>
  new Promise((resolve) => {
    execFile(file, args, { timeout: timeoutMs, maxBuffer: 4 * 1024 * 1024, killSignal: "SIGKILL" }, (err, stdout, stderr) => {
      const e = err as (NodeJS.ErrnoException & { killed?: boolean; code?: number | string }) | null;
      resolve({
        stdout: String(stdout),
        stderr: e && e.code === "ENOENT" ? "docker not found on PATH" : String(stderr),
        code: e ? (typeof e.code === "number" ? e.code : null) : 0,
        timedOut: Boolean(e?.killed),
      });
    });
  });

export interface ShellOptions {
  image: string;
  timeoutMs: number;
  network: string;
  exec?: ExecFn;
  maxOutput?: number;
}

const truncate = (s: string, max: number) => (s.length > max ? `${s.slice(0, max)}\n...[truncated ${s.length - max} chars]` : s);

/** Build the docker argv. Exposed for tests. */
export function dockerArgs(opts: Pick<ShellOptions, "image" | "network">, workspace: string, command: string, name: string): string[] {
  return [
    "run", "--rm", "--name", name,
    "--network", opts.network,
    "--memory", "512m", "--cpus", "1", "--pids-limit", "256",
    "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
    "-v", `${workspace}:/workspace`, "-w", "/workspace",
    opts.image, "sh", "-c", command,
  ];
}

export function shellTool(opts: ShellOptions): Tool {
  const exec = opts.exec ?? defaultExec;
  const maxOutput = opts.maxOutput ?? 20_000;
  return {
    name: "shell",
    description:
      "Run a shell command inside a disposable Docker container. The workspace folder is mounted at /workspace (the working directory). No network by default.",
    inputSchema: {
      type: "object",
      properties: { command: { type: "string", description: "Command to run with sh -c" } },
      required: ["command"],
    },
    async run(input, ctx) {
      const command = input.command;
      if (typeof command !== "string" || !command.trim()) throw new Error("command must be a non-empty string");
      const name = `agent-${process.pid}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      const res = await exec("docker", dockerArgs(opts, ctx.workspace, command, name), opts.timeoutMs);
      if (res.timedOut) {
        // The docker client was killed; make sure the container goes away too.
        await exec("docker", ["rm", "-f", name], 10_000).catch(() => undefined);
        throw new Error(`command timed out after ${opts.timeoutMs}ms`);
      }
      const parts = [`exit code: ${res.code ?? "unknown"}`];
      if (res.stdout) parts.push(`stdout:\n${truncate(res.stdout, maxOutput)}`);
      if (res.stderr) parts.push(`stderr:\n${truncate(res.stderr, maxOutput)}`);
      const text = parts.join("\n");
      if (res.code !== 0) throw new Error(text);
      return text;
    },
  };
}
