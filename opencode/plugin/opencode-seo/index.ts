import { Plugin } from "@opencode/plugin"
import { spawn, spawnSync } from "node:child_process"
import { existsSync } from "node:fs"
import { readFile, realpath, stat } from "node:fs/promises"
import { homedir } from "node:os"
import path from "node:path"
import { fileURLToPath } from "node:url"

const MAX_OUTPUT_BYTES = 2_000_000
const MAX_READ_BYTES = 1_000_000
const DEFAULT_TIMEOUT_MS = 120_000
const MAX_TIMEOUT_MS = 15 * 60_000

type PythonCommand = {
  command: string
  prefix: string[]
}

type ProcessResult = {
  code: number
  stdout: string
  stderr: string
  timedOut: boolean
}

function currentPluginDir(): string {
  return path.dirname(fileURLToPath(import.meta.url))
}

function isRuntimeRoot(directory: string): boolean {
  return existsSync(path.join(directory, "scripts", "runtime.py"))
}

function resolveRoot(workspace: string): string {
  const pluginDir = currentPluginDir()
  const candidates = [
    process.env.OPENCODE_SEO_ROOT,
    path.resolve(pluginDir, "../../.."),
    path.resolve(pluginDir, "../../opencode-seo"),
    workspace,
    process.cwd(),
  ].filter((value): value is string => Boolean(value))

  for (const candidate of candidates) {
    if (isRuntimeRoot(candidate)) return candidate
  }

  return workspace || candidates[0] || process.cwd()
}

function resolveAssetsRoot(runtimeRoot: string, workspace: string): string {
  const pluginDir = currentPluginDir()
  // In a repository checkout every asset exists twice: the canonical
  // Claude-compatible copy at the runtime root and the generated
  // OpenCode-native copy under `.opencode/`. Reads must prefer the generated
  // copy so `seo({"action": "read"})` never returns Claude-only instructions
  // such as `${CLAUDE_PLUGIN_ROOT}` launcher commands to an OpenCode agent.
  const candidates = [
    path.join(runtimeRoot, ".opencode"),
    runtimeRoot,
    path.resolve(pluginDir, "../.."),
    workspace,
    path.resolve(runtimeRoot, ".."),
  ]

  for (const candidate of candidates) {
    if (existsSync(path.join(candidate, "skills"))) return candidate
  }

  return runtimeRoot
}

function pythonCandidates(): PythonCommand[] {
  const configured = [process.env.OPENCODE_SEO_PYTHON, process.env.CLAUDE_SEO_PYTHON].filter(
    (value): value is string => Boolean(value),
  )
  const candidates: PythonCommand[] = configured.map((command) => ({ command, prefix: [] }))

  if (process.platform === "win32") {
    candidates.push({ command: "py", prefix: ["-3"] })
  }

  candidates.push({ command: "python3", prefix: [] })
  candidates.push({ command: "python", prefix: [] })
  return candidates
}

const DOCTOR_TTL_MS = 5 * 60_000
const PYTHON_STORAGE_KEY = "python/interpreter"
const DOCTOR_STORAGE_KEY = "runtime/doctor"

const SEO_SUBCOMMANDS = new Set([
  "agentic",
  "ahrefs",
  "audit",
  "backlinks",
  "bing",
  "cluster",
  "competitor-pages",
  "content",
  "content-brief",
  "dataforseo",
  "doctor",
  "drift",
  "ecommerce",
  "firecrawl",
  "flow",
  "geo",
  "google",
  "hreflang",
  "image-gen",
  "images",
  "local",
  "maps",
  "matomo",
  "page",
  "plan",
  "profound",
  "programmatic",
  "schema",
  "seranking",
  "setup",
  "sitemap",
  "sxo",
  "technical",
  "unlighthouse",
])

type StoredDoctor = {
  at: number
  version: string
  content: string
}

function storedPython(value: unknown): PythonCommand | undefined {
  const payload = value as { command?: unknown; prefix?: unknown } | undefined
  if (!payload || typeof payload.command !== "string" || !payload.command) return undefined
  const prefix = Array.isArray(payload.prefix)
    ? payload.prefix.filter((part): part is string => typeof part === "string")
    : []
  return { command: payload.command, prefix }
}

function storedDoctor(value: unknown): StoredDoctor | undefined {
  const payload = value as { at?: unknown; version?: unknown; content?: unknown } | undefined
  if (
    !payload ||
    typeof payload.at !== "number" ||
    typeof payload.version !== "string" ||
    typeof payload.content !== "string"
  ) {
    return undefined
  }
  return { at: payload.at, version: payload.version, content: payload.content }
}

function isSeoSkillSelection(value: unknown): boolean {
  if (typeof value === "string") return value.startsWith("seo")
  const id = (value as { id?: unknown } | undefined)?.id
  return typeof id === "string" && id.startsWith("seo")
}

// Rewrite a bare "seo <subcommand> ..." prompt into an explicit skill
// instruction. Slash commands already do this, so leave them untouched, and
// ignore anything that does not start with the seo keyword.
function seoPromptHint(text: string): string | undefined {
  const trimmed = text.trimStart()
  if (!trimmed || trimmed.startsWith("/")) return undefined
  const match = /^seo(?:\s+([a-z][a-z-]*))?\b/i.exec(trimmed)
  if (!match) return undefined
  const subcommand = (match[1] ?? "").toLowerCase()
  if (subcommand && !SEO_SUBCOMMANDS.has(subcommand)) return undefined
  return subcommand
    ? `The user wants the \`seo\` workflow \`${subcommand}\`. Load the \`seo\` skill and the matching \`seo-*\` sub-skill before answering, then follow that workflow.`
    : "The user wants an SEO task. Load the `seo` skill before answering and route to the matching `seo-*` sub-skill."
}

async function readPluginVersion(): Promise<string> {
  try {
    const raw = await readFile(path.join(currentPluginDir(), "package.json"), "utf8")
    const parsed = JSON.parse(raw) as { version?: unknown }
    return typeof parsed.version === "string" ? parsed.version : "unknown"
  } catch {
    return "unknown"
  }
}

function findPython(): PythonCommand | undefined {
  for (const candidate of pythonCandidates()) {
    if (pythonWorks(candidate)) return candidate
  }

  return undefined
}

function pythonWorks(candidate: PythonCommand): boolean {
  const result = spawnSync(candidate.command, [...candidate.prefix, "-c", "import sys"], {
    encoding: "utf8",
    timeout: 5_000,
    windowsHide: true,
  })
  return result.status === 0
}

function clip(value: string): string {
  if (Buffer.byteLength(value, "utf8") <= MAX_OUTPUT_BYTES) return value
  return `${value.slice(0, MAX_OUTPUT_BYTES)}\n[output truncated]`
}

function runProcess(
  python: PythonCommand,
  args: string[],
  options: { cwd: string; timeout: number; signal?: AbortSignal; env?: NodeJS.ProcessEnv },
): Promise<ProcessResult> {
  return new Promise((resolve) => {
    let settled = false
    let stdout = ""
    let stderr = ""
    let timedOut = false
    let timer: ReturnType<typeof setTimeout> | undefined

    const child = spawn(python.command, [...python.prefix, ...args], {
      cwd: options.cwd,
      windowsHide: true,
      env: {
        ...process.env,
        ...options.env,
        PYTHONUTF8: "1",
        PYTHONIOENCODING: "utf-8",
      },
    })

    const abort = () => {
      child.kill()
      finish(130)
    }

    const finish = (code: number) => {
      if (settled) return
      settled = true
      if (timer) clearTimeout(timer)
      options.signal?.removeEventListener("abort", abort)
      resolve({ code, stdout: clip(stdout), stderr: clip(stderr), timedOut })
    }

    const collect = (chunk: Buffer, target: "stdout" | "stderr") => {
      const text = chunk.toString("utf8")
      if (target === "stdout") {
        if (stdout.length < MAX_OUTPUT_BYTES * 2) stdout += text
      } else if (stderr.length < MAX_OUTPUT_BYTES * 2) {
        stderr += text
      }
    }

    child.stdout?.on("data", (chunk: Buffer) => collect(chunk, "stdout"))
    child.stderr?.on("data", (chunk: Buffer) => collect(chunk, "stderr"))

    child.on("error", (error) => {
      stderr += error.message
      finish(127)
    })

    child.on("close", (code) => finish(code ?? 1))

    timer = setTimeout(() => {
      timedOut = true
      child.kill()
      finish(124)
    }, options.timeout)

    options.signal?.addEventListener("abort", abort, { once: true })
  })
}

function safeReadPath(base: string, relative: string): string | undefined {
  if (path.isAbsolute(relative)) return undefined
  const normalized = relative.replaceAll("\\", "/")
  if (normalized.split("/").some((segment) => segment === "..")) return undefined

  const candidate = path.resolve(base, normalized)
  const root = path.resolve(base)
  if (candidate !== root && !candidate.startsWith(`${root}${path.sep}`)) return undefined
  return candidate
}

async function readAsset(runtimeRoot: string, assetsRoot: string, relative: string): Promise<string> {
  const roots = [assetsRoot, runtimeRoot]
  for (const root of roots) {
    const candidate = safeReadPath(root, relative)
    if (!candidate) continue

    try {
      const resolved = await realpath(candidate)
      const rootResolved = await realpath(root)
      if (resolved !== rootResolved && !resolved.startsWith(`${rootResolved}${path.sep}`)) continue
      const info = await stat(resolved)
      if (!info.isFile() || info.size > MAX_READ_BYTES) continue
      return await readFile(resolved, "utf8")
    } catch {
      continue
    }
  }

  throw new Error(`File not found or not readable inside the SEO install root: ${relative}`)
}

function appendToolText(result: unknown, text: string): unknown {
  const payload = result as { content?: unknown } | undefined
  if (!payload) return { content: text }

  if (typeof payload.content === "string") {
    return { ...payload, content: `${payload.content}\n\n${text}` }
  }

  if (Array.isArray(payload.content)) {
    return { ...payload, content: [...payload.content, { type: "text", text }] }
  }

  return { ...payload, content: text }
}

// validate-schema.py speaks the Claude Code hook protocol: warnings arrive as
// `{"hookSpecificOutput": {"additionalContext": "..."}}` on stdout, while
// critical findings go to stderr with exit code 2. OpenCode appends this text
// to the tool result, so unwrap the envelope and keep the message readable.
function schemaHookText(result: ProcessResult): string {
  let text = result.stdout.trim()
  if (text.startsWith("{")) {
    try {
      const payload = JSON.parse(text) as {
        hookSpecificOutput?: { additionalContext?: unknown }
      }
      const context = payload.hookSpecificOutput?.additionalContext
      if (typeof context === "string" && context.trim()) text = context.trim()
    } catch {
      // Not the hook envelope; keep the raw output.
    }
  }

  const stderr = result.code === 2 ? result.stderr.trim() : ""
  return [text, stderr].filter(Boolean).join("\n").trim()
}

export default Plugin.define({
  id: "opencode-seo",
  async setup(ctx) {
    const workspace = ctx.location.directory
    const runtimeRoot = resolveRoot(workspace)
    const assetsRoot = resolveAssetsRoot(runtimeRoot, workspace)
    const runtime = path.join(runtimeRoot, "scripts", "runtime.py")
    const seoEnv: NodeJS.ProcessEnv = {
      OPENCODE_SEO_ROOT: runtimeRoot,
      OPENCODE_SEO_CONFIG_DIR:
        process.env.OPENCODE_SEO_CONFIG_DIR ??
        process.env.CLAUDE_SEO_CONFIG_DIR ??
        path.join(homedir(), ".config", "opencode-seo"),
      OPENCODE_SEO_CACHE_DIR:
        process.env.OPENCODE_SEO_CACHE_DIR ??
        process.env.CLAUDE_SEO_CACHE_DIR ??
        path.join(homedir(), ".cache", "opencode-seo"),
    }
    const pluginVersion = await readPluginVersion()

    let pythonCache: PythonCommand | undefined
    let pythonLoaded = false
    const resolvePython = async (): Promise<PythonCommand | undefined> => {
      if (pythonLoaded) return pythonCache
      pythonLoaded = true

      const remembered = storedPython(
        await ctx.storage.get(PYTHON_STORAGE_KEY).catch(() => undefined),
      )
      if (remembered && pythonWorks(remembered)) {
        pythonCache = remembered
        return pythonCache
      }

      pythonCache = findPython()
      if (pythonCache) {
        await ctx.storage.set(PYTHON_STORAGE_KEY, pythonCache).catch(() => undefined)
      }
      return pythonCache
    }

    await ctx.tool.transform((editor) => {
      editor.add({
        name: "seo",
        description:
          "Run the bundled OpenCode SEO Python runtime. Use action run with a script name and arguments, setup or doctor for runtime maintenance, path for the install root, or read for a bundled reference file. Set refresh to bypass the cached doctor result.",
        input: {
          type: "object",
          properties: {
            action: {
              type: "string",
              enum: ["run", "setup", "doctor", "path", "read"],
              description: "Operation to perform.",
            },
            script: {
              type: "string",
              description: "Script file name for action run, for example page_checks.py.",
            },
            extension: {
              type: "string",
              description: "Optional extension name, for example banana.",
            },
            args: {
              type: "array",
              items: { type: "string" },
              description: "Arguments passed to the script.",
            },
            path: {
              type: "string",
              description: "Relative reference path for action read.",
            },
            timeout: {
              type: "number",
              description: "Timeout in milliseconds for action run or setup.",
            },
            refresh: {
              type: "boolean",
              description: "Bypass the cached doctor result and probe the runtime again.",
            },
          },
          required: ["action"],
          additionalProperties: false,
        },
        options: { codemode: false },
        execute: async (input, context) => {
          const request = input as {
            action: "run" | "setup" | "doctor" | "path" | "read"
            script?: string
            extension?: string
            args?: string[]
            path?: string
            timeout?: number
            refresh?: boolean
          }

          const source =
            context.messageID && context.id
              ? { type: "tool" as const, messageID: context.messageID, id: context.id }
              : undefined
          // Permission failures must propagate as Tool.Error so OpenCode can
          // stop the call. Catch only the work that follows the check.
          await ctx.permission.assert({
            sessionID: context.sessionID,
            agent: context.agent,
            ...(source ? { source } : {}),
            action: "seo",
            resources: [
              request.action,
              request.script ?? request.path ?? "",
              request.extension ?? "",
            ].filter(Boolean),
          })

          try {
            if (request.action === "doctor" && !request.refresh) {
              const cached = storedDoctor(
                await ctx.storage.get(DOCTOR_STORAGE_KEY).catch(() => undefined),
              )
              if (
                cached &&
                cached.version === pluginVersion &&
                Date.now() - cached.at < DOCTOR_TTL_MS
              ) {
                return { content: cached.content }
              }
            }

            if (request.action === "path") {
              return { content: runtimeRoot }
            }

            if (request.action === "read") {
              if (!request.path) throw new Error("action read requires path")
              return { content: await readAsset(runtimeRoot, assetsRoot, request.path) }
            }

            const python = await resolvePython()
            if (!python) {
              return {
                content:
                  "ERROR: no supported Python interpreter found. Install Python 3.11-3.14 or set OPENCODE_SEO_PYTHON.",
              }
            }

            const timeout = Math.min(
              Math.max(request.timeout ?? DEFAULT_TIMEOUT_MS, 1_000),
              MAX_TIMEOUT_MS,
            )
            let args: string[]

            if (request.action === "run") {
              if (!request.script || !/^[A-Za-z0-9][A-Za-z0-9_-]*\.py$/.test(request.script)) {
                throw new Error("action run requires a script name such as page_checks.py")
              }
              if (request.extension && !/^[a-z0-9][a-z0-9-]*$/.test(request.extension)) {
                throw new Error("extension must be lowercase letters, digits, and hyphens")
              }
              args = request.extension
                ? [runtime, "run", "--extension", request.extension, request.script, ...(request.args ?? [])]
                : [runtime, "run", request.script, ...(request.args ?? [])]
            } else if (request.action === "setup") {
              args = [runtime, "setup"]
            } else {
              args = [runtime, "doctor", "--json"]
            }

            const result = await runProcess(python, args, {
              cwd: workspace,
              timeout,
              signal: context.signal,
              env: seoEnv,
            })

            const output = [result.stdout.trim(), result.stderr.trim()].filter(Boolean).join("\n")
            const prefix = result.timedOut
              ? `ERROR: command timed out after ${timeout} ms`
              : result.code === 0
                ? ""
                : `ERROR: command exited with code ${result.code}`
            const content = [prefix, output].filter(Boolean).join("\n") || "OK"

            // Cache a passing doctor probe briefly so repeated checks do not
            // spawn Python. Any setup attempt invalidates it, because the
            // environment may have changed underneath the cache.
            if (request.action === "doctor" && !prefix && !result.timedOut) {
              await ctx.storage
                .set(DOCTOR_STORAGE_KEY, { at: Date.now(), version: pluginVersion, content })
                .catch(() => undefined)
            }
            if (request.action === "setup") {
              await ctx.storage.remove(DOCTOR_STORAGE_KEY).catch(() => undefined)
            }

            return { content }
          } catch (error) {
            const message = error instanceof Error ? error.message : String(error)
            return { content: `ERROR: ${message}` }
          }
        },
      })
    })

    await ctx.tool.hook("execute.after", async (event) => {
      if (event.status !== "completed") return
      if (!["write", "edit", "patch"].includes(event.tool)) return

      try {
        const raw = event as unknown as { input?: Record<string, unknown> }
        const file = raw.input?.path ?? raw.input?.filePath
        if (typeof file !== "string" || !/\.(html?|jsx|tsx|vue|svelte|php|ejs)$/i.test(file)) return
        const resolvedFile = path.isAbsolute(file) ? file : path.resolve(workspace, file)
        if (!existsSync(resolvedFile)) return

        const python = await resolvePython()
        if (!python) return

        const hookScript = path.join(runtimeRoot, "hooks", "validate-schema.py")
        if (!existsSync(hookScript)) return

        const result = await runProcess(python, [hookScript, resolvedFile], {
          cwd: workspace,
          timeout: 30_000,
          env: seoEnv,
        })

        const text = schemaHookText(result)
        if (!text) return

        event.result = appendToolText(event.result, `[schema validation]\n${text}`) as typeof event.result
      } catch {
        return
      }
    })

    // Auto-route a bare "seo <subcommand> ..." prompt to the matching skill.
    // Slash commands are already explicit, and prompts that selected a seo
    // skill are left untouched.
    await ctx.session.hook("prompt", (event) => {
      const text = typeof event.prompt.text === "string" ? event.prompt.text : ""
      if (!text.trim()) return
      const selected = event.prompt.skills
      if (Array.isArray(selected) && selected.some(isSeoSkillSelection)) return
      const hint = seoPromptHint(text)
      if (!hint) return
      event.prompt.text = `${hint}\n\n${text}`
      event.metadata = {
        ...(event.metadata as Record<string, unknown> | undefined),
        seoRouted: true,
      }
    })
  },
})
