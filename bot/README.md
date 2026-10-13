# agent-bot — Phase 1

A single tool-calling agent loop in TypeScript (Node 22). It calls a model, runs the tools the model asks for, and repeats until the model finishes or a limit is hit.

## Requirements

- Node 22+
- Docker (running daemon) for the `shell` tool
- An API key for your model provider

## Setup

```bash
cd bot
npm install
cp .env.example .env     # then edit .env; it is read automatically (real environment variables win)
```

## Run

```bash
export ANTHROPIC_API_KEY=sk-...
npm start -- "Create hello.py that prints the first 10 primes, run it, and tell me the output"

npm start -- --id my-task "start a task"      # name the conversation
npm start -- --resume my-task "now do more"   # continue it
npm start -- --list                           # saved conversations
```

Tool activity goes to stderr, the model's text to stdout, and a final line reports the stop reason, turns and tokens.

## Tests

```bash
npm test          # vitest, no network or Docker needed
npm run typecheck
```

## Model provider (environment variables)

| Variable | Default | Notes |
|---|---|---|
| `MODEL_PROVIDER` | `anthropic` | `anthropic` or `openai` (any OpenAI-compatible endpoint) |
| `MODEL_NAME` | `claude-sonnet-5-5` / `gpt-4o` | |
| `ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL` | | |
| `OPENAI_API_KEY`, `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Ollama: `http://localhost:11434/v1` |
| `MODEL_MAX_OUTPUT_TOKENS` | `4096` | per model call |

`src/model/` exposes `complete(messages, tools, { system }) -> AsyncIterable<ModelEvent>`. Events are `text`, `tool_call`, `usage`, `done`. Phase 1 calls providers without streaming and replays the response as events; the interface leaves room for real streaming.

## Limits

| Variable | Default | Stop reason |
|---|---|---|
| `MAX_TURNS` | 20 | `turn_limit` |
| `MAX_TOTAL_TOKENS` | 200000 | `token_limit` (input + output summed over all turns) |
| `MAX_DEPTH` | 3 | `depth_limit` (nesting depth of the agent; nothing spawns sub-agents until a later phase) |

Limits are checked between turns, after tool results are recorded, so a stopped conversation is always valid to resume. Other stop reasons: `finished`, `output_truncated`, `error`.

## Tools

- **`shell`** runs `sh -c` in a throwaway `docker run --rm` container: no network (`SHELL_NETWORK`), 512 MB, 1 CPU, all capabilities dropped, timeout (`SHELL_TIMEOUT_MS`). Only `WORKSPACE_DIR` is mounted, at `/workspace`. Image: `SHELL_IMAGE` (default `alpine:3.20`, which has no Python; use `python:3.12-alpine` for Python tasks).
- **`read_file` / `write_file`** operate inside `WORKSPACE_DIR`. `..` traversal, absolute paths and symlinks pointing outside are rejected.
- **`fetch_url`** fetches http(s) pages, reduces HTML to text, caps size and time, and refuses loopback/private/link-local addresses (including via DNS).

## History

Each conversation is a JSONL file in `HISTORY_DIR` (default `./.history`), one message per line, appended as the run progresses.

## Layout

```
src/loop.ts       agent loop and limits
src/model/        provider adapters (anthropic, openai-compatible) + mock for tests
src/tools/        shell, files, fetch
src/history.ts    JSONL conversation store
src/cli.ts        command-line entry point
tests/
```
