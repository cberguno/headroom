import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { HistoryStore } from "../src/history.js";
import { runAgent } from "../src/loop.js";
import { createMockModel } from "../src/model/mock.js";
import type { Message } from "../src/types.js";
import { call, echoTool, limits, say } from "./helpers.js";

let dir: string;
beforeEach(async () => { dir = await fs.mkdtemp(path.join(os.tmpdir(), "hist-")); });
afterEach(async () => { await fs.rm(dir, { recursive: true, force: true }); });

describe("history", () => {
  it("round-trips messages and lists conversations", async () => {
    const h = new HistoryStore(dir);
    await h.append("a", { role: "user", content: [{ type: "text", text: "hi" }] });
    await h.append("a", { role: "assistant", content: [{ type: "text", text: "yo" }] });
    expect(await h.load("a")).toHaveLength(2);
    expect(await h.list()).toEqual(["a"]);
  });

  it("errors clearly for unknown ids and rejects path-like ids", async () => {
    const h = new HistoryStore(dir);
    await expect(h.load("missing")).rejects.toThrow(/no saved conversation/);
    await expect(h.load("../etc/passwd")).rejects.toThrow(/invalid conversation id/);
  });

  it("resumes a saved conversation through the loop", async () => {
    const h = new HistoryStore(dir);
    const base = { tools: [echoTool], limits, workspace: dir, onMessage: (m: Message) => h.append("c1", m) };
    await runAgent({ ...base, model: createMockModel([call("1", "echo", { text: "x" }), say("first done")]), input: "start" });

    const model2 = createMockModel([say("second done")]);
    const r = await runAgent({ ...base, model: model2, messages: await h.load("c1"), input: "continue" });
    expect(r.finalText).toBe("second done");
    const sent = JSON.stringify(model2.calls[0]!.messages);
    expect(sent).toContain("start");
    expect(sent).toContain("echo:x");
    expect(await h.load("c1")).toHaveLength(6); // 4 from the first run + 2 from the resumed run
  });
});
