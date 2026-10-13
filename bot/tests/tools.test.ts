import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fetchTool, htmlToText, isPrivateIp } from "../src/tools/fetch.js";
import { readFileTool, writeFileTool } from "../src/tools/files.js";
import { dockerArgs, shellTool, type ExecFn } from "../src/tools/shell.js";

let ws: string;
beforeEach(async () => { ws = await fs.mkdtemp(path.join(os.tmpdir(), "ws-")); });
afterEach(async () => { await fs.rm(ws, { recursive: true, force: true }); });
const ctx = () => ({ workspace: ws });

describe("file tools", () => {
  it("writes then reads a file, creating parent dirs", async () => {
    await writeFileTool.run({ path: "a/b/c.txt", content: "hello" }, ctx());
    expect(await fs.readFile(path.join(ws, "a/b/c.txt"), "utf8")).toBe("hello");
    expect(await readFileTool.run({ path: "a/b/c.txt" }, ctx())).toBe("hello");
  });

  it("overwrites existing files", async () => {
    await writeFileTool.run({ path: "f", content: "one" }, ctx());
    await writeFileTool.run({ path: "f", content: "two" }, ctx());
    expect(await readFileTool.run({ path: "f" }, ctx())).toBe("two");
  });

  it("rejects .. traversal and absolute paths outside the workspace", async () => {
    await expect(readFileTool.run({ path: "../secret" }, ctx())).rejects.toThrow(/escapes/);
    await expect(writeFileTool.run({ path: "/etc/evil", content: "x" }, ctx())).rejects.toThrow(/escapes/);
  });

  it("rejects symlinks that point outside the workspace", async () => {
    const outside = await fs.mkdtemp(path.join(os.tmpdir(), "outside-"));
    await fs.writeFile(path.join(outside, "s.txt"), "secret");
    await fs.symlink(outside, path.join(ws, "link"));
    await expect(readFileTool.run({ path: "link/s.txt" }, ctx())).rejects.toThrow(/symlink/);
    await expect(writeFileTool.run({ path: "link/new.txt", content: "x" }, ctx())).rejects.toThrow(/symlink/);
    await fs.rm(outside, { recursive: true, force: true });
  });

  it("errors on missing files and bad input", async () => {
    await expect(readFileTool.run({ path: "nope.txt" }, ctx())).rejects.toThrow();
    await expect(writeFileTool.run({ path: "x" }, ctx())).rejects.toThrow(/content/);
    await expect(readFileTool.run({}, ctx())).rejects.toThrow(/path/);
  });
});

describe("shell tool", () => {
  const opts = { image: "alpine:3.20", timeoutMs: 1000, network: "none" };

  it("builds a locked-down docker invocation mounting only the workspace", () => {
    const args = dockerArgs(opts, "/w", "ls", "n1");
    expect(args).toEqual(expect.arrayContaining(["--rm", "--network", "none", "-v", "/w:/workspace", "alpine:3.20"]));
    expect(args.slice(-3)).toEqual(["sh", "-c", "ls"]);
    expect(args).toEqual(expect.arrayContaining(["--cap-drop", "ALL", "--memory", "512m"]));
  });

  it("returns exit code and output on success", async () => {
    const exec: ExecFn = vi.fn(async () => ({ stdout: "hi\n", stderr: "", code: 0, timedOut: false }));
    const out = await shellTool({ ...opts, exec }).run({ command: "echo hi" }, ctx());
    expect(out).toContain("exit code: 0");
    expect(out).toContain("hi");
    const runCall = vi.mocked(exec).mock.calls.find((c) => c[1][0] === "run")!;
    expect(runCall[0]).toBe("docker");
    expect(runCall[1]).toContain(`${ws}:/workspace`);
  });

  it("raises an error carrying output for non-zero exits", async () => {
    const exec: ExecFn = async (_f, args) => ({ stdout: "", stderr: "bad", code: args[0] === "run" ? 2 : 0, timedOut: false });
    await expect(shellTool({ ...opts, exec }).run({ command: "false" }, ctx())).rejects.toThrow(/exit code: 2[\s\S]*bad/);
  });

  it("pulls a missing image before running, and only checks once", async () => {
    const calls: string[] = [];
    const exec: ExecFn = async (_f, args) => {
      calls.push(args.slice(0, 2).join(" "));
      return { stdout: "", stderr: "", code: args[0] === "image" ? 1 : 0, timedOut: false };
    };
    const tool = shellTool({ ...opts, exec });
    await tool.run({ command: "a" }, ctx());
    await tool.run({ command: "b" }, ctx());
    expect(calls).toEqual(["image inspect", "pull alpine:3.20", "run --rm", "run --rm"]);
  });

  it("kills the container and errors on timeout", async () => {
    const exec = vi.fn<ExecFn>(async (_f, args) => ({ stdout: "", stderr: "", code: args[0] === "run" ? null : 0, timedOut: args[0] === "run" }));
    await expect(shellTool({ ...opts, exec }).run({ command: "sleep 99" }, ctx())).rejects.toThrow(/timed out/);
    expect(exec.mock.calls.at(-1)![1].slice(0, 2)).toEqual(["rm", "-f"]);
  });

  it("truncates huge output and validates input", async () => {
    const exec: ExecFn = async () => ({ stdout: "x".repeat(500), stderr: "", code: 0, timedOut: false });
    const out = await shellTool({ ...opts, exec, maxOutput: 100 }).run({ command: "yes" }, ctx());
    expect(out).toContain("[truncated 400 chars]");
    await expect(shellTool({ ...opts, exec }).run({ command: "  " }, ctx())).rejects.toThrow(/command/);
  });
});

const page = (body: string, type = "text/html", status = 200) =>
  vi.fn(async () => new Response(body, { status, headers: { "content-type": type } })) as unknown as typeof fetch;
const publicLookup = async () => ["93.184.216.34"];

describe("fetch tool", () => {
  it("fetches a page and reduces HTML to text", async () => {
    const tool = fetchTool({ fetchImpl: page("<html><style>x{}</style><h1>Title</h1><p>Hello &amp; bye</p><script>evil()</script></html>"), lookup: publicLookup });
    const out = await tool.run({ url: "https://example.com/" }, ctx());
    expect(out).toContain("HTTP 200 https://example.com/");
    expect(out).toContain("Title");
    expect(out).toContain("Hello & bye");
    expect(out).not.toContain("evil");
    expect(out).not.toContain("<h1>");
  });

  it("returns non-HTML bodies untouched and truncates long pages", async () => {
    const tool = fetchTool({ fetchImpl: page("a".repeat(50), "text/plain"), lookup: publicLookup, maxBytes: 10 });
    const out = await tool.run({ url: "https://example.com/x.txt" }, ctx());
    expect(out).toContain("aaaaaaaaaa");
    expect(out).toContain("truncated");
  });

  it("errors on HTTP failures, bad URLs and non-http protocols", async () => {
    await expect(fetchTool({ fetchImpl: page("nope", "text/plain", 404), lookup: publicLookup }).run({ url: "https://e.com" }, ctx())).rejects.toThrow(/HTTP 404/);
    await expect(fetchTool().run({ url: "not a url" }, ctx())).rejects.toThrow(/invalid URL/);
    await expect(fetchTool().run({ url: "file:///etc/passwd" }, ctx())).rejects.toThrow(/protocol/);
  });

  it("refuses private and loopback addresses, including via DNS", async () => {
    const fetchImpl = page("x");
    const tool = fetchTool({ fetchImpl, lookup: async () => ["10.0.0.5"] });
    await expect(tool.run({ url: "http://127.0.0.1:8080" }, ctx())).rejects.toThrow(/private/);
    await expect(tool.run({ url: "http://localhost/" }, ctx())).rejects.toThrow(/private/);
    await expect(tool.run({ url: "http://internal.example/" }, ctx())).rejects.toThrow(/private/);
    await expect(tool.run({ url: "http://[::1]/" }, ctx())).rejects.toThrow(/private/);
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("classifies IPs", () => {
    for (const ip of ["10.1.1.1", "127.0.0.1", "169.254.169.254", "172.16.0.1", "192.168.1.1", "::1", "fd00::1", "::ffff:10.0.0.1"]) expect(isPrivateIp(ip)).toBe(true);
    for (const ip of ["8.8.8.8", "172.32.0.1", "93.184.216.34"]) expect(isPrivateIp(ip)).toBe(false);
    expect(htmlToText("<p>a</p><p>b</p>")).toBe("a\nb");
  });
});
