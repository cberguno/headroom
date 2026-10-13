import dns from "node:dns/promises";
import net from "node:net";
import type { Tool } from "../types.js";

type FetchLike = typeof fetch;
type LookupFn = (host: string) => Promise<string[]>;

export interface FetchToolOptions {
  fetchImpl?: FetchLike;
  lookup?: LookupFn;
  timeoutMs?: number;
  maxBytes?: number;
  allowPrivate?: boolean;
}

export function isPrivateIp(ip: string): boolean {
  if (net.isIPv4(ip)) {
    const [a, b] = ip.split(".").map(Number) as [number, number];
    return a === 10 || a === 127 || a === 0 || (a === 169 && b === 254) || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168);
  }
  const v = ip.toLowerCase();
  if (v.startsWith("::ffff:")) return isPrivateIp(v.slice(7));
  return v === "::1" || v === "::" || v.startsWith("fc") || v.startsWith("fd") || v.startsWith("fe80");
}

const defaultLookup: LookupFn = async (host) => (await dns.lookup(host, { all: true })).map((r) => r.address);

export function htmlToText(html: string): string {
  return html
    .replace(/<(script|style|noscript)[\s\S]*?<\/\1>/gi, "")
    .replace(/<!--[\s\S]*?-->/g, "")
    .replace(/<\/(p|div|br|li|h[1-6]|tr)>|<br\s*\/?>/gi, "\n")
    .replace(/<[^>]+>/g, "")
    .replace(/&nbsp;/g, " ").replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#39;/g, "'")
    .replace(/[ \t]+/g, " ")
    .replace(/\n\s*\n+/g, "\n\n")
    .trim();
}

export function fetchTool(opts: FetchToolOptions = {}): Tool {
  const fetchImpl = opts.fetchImpl ?? fetch;
  const lookup = opts.lookup ?? defaultLookup;
  const timeoutMs = opts.timeoutMs ?? 15_000;
  const maxBytes = opts.maxBytes ?? 200_000;
  return {
    name: "fetch_url",
    description: "Fetch a web page over http(s) and return its text content (HTML is reduced to plain text).",
    inputSchema: {
      type: "object",
      properties: { url: { type: "string", description: "Absolute http or https URL" } },
      required: ["url"],
    },
    async run(input) {
      let url: URL;
      try {
        url = new URL(String(input.url));
      } catch {
        throw new Error(`invalid URL: ${String(input.url)}`);
      }
      if (url.protocol !== "http:" && url.protocol !== "https:") throw new Error(`unsupported protocol: ${url.protocol}`);
      if (!opts.allowPrivate) {
        const host = url.hostname.replace(/^\[|\]$/g, "");
        const addrs = net.isIP(host) ? [host] : await lookup(host);
        if (host === "localhost" || addrs.some(isPrivateIp)) throw new Error(`refusing to fetch private/internal address: ${host}`);
      }
      const res = await fetchImpl(url, { signal: AbortSignal.timeout(timeoutMs), headers: { "user-agent": "agent-bot/0.1" } });
      const raw = await res.text();
      const clipped = raw.length > maxBytes ? raw.slice(0, maxBytes) : raw;
      const type = res.headers.get("content-type") ?? "";
      let body = /html/i.test(type) || /^\s*<(!doctype|html)/i.test(clipped) ? htmlToText(clipped) : clipped;
      if (raw.length > maxBytes) body += `\n...[truncated, page larger than ${maxBytes} chars]`;
      const head = `HTTP ${res.status} ${url.href}`;
      if (!res.ok) throw new Error(`${head}\n${body.slice(0, 1000)}`);
      return `${head}\n\n${body}`;
    },
  };
}
