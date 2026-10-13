import fs from "node:fs/promises";
import path from "node:path";
import type { Message } from "./types.js";

const ID_RE = /^[A-Za-z0-9_-]+$/;

export class HistoryStore {
  constructor(private dir: string) {}

  private file(id: string): string {
    if (!ID_RE.test(id)) throw new Error(`invalid conversation id: ${id}`);
    return path.join(this.dir, `${id}.jsonl`);
  }

  async append(id: string, message: Message): Promise<void> {
    await fs.mkdir(this.dir, { recursive: true });
    await fs.appendFile(this.file(id), JSON.stringify(message) + "\n", "utf8");
  }

  async load(id: string): Promise<Message[]> {
    let text: string;
    try {
      text = await fs.readFile(this.file(id), "utf8");
    } catch (e) {
      if ((e as NodeJS.ErrnoException).code === "ENOENT") throw new Error(`no saved conversation "${id}"`);
      throw e;
    }
    return text.split("\n").filter(Boolean).map((l) => JSON.parse(l) as Message);
  }

  async list(): Promise<string[]> {
    try {
      return (await fs.readdir(this.dir)).filter((f) => f.endsWith(".jsonl")).map((f) => f.slice(0, -6)).sort();
    } catch {
      return [];
    }
  }
}
