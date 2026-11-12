import { Plugin } from "@opencode/plugin"
import { spawn, spawnSync } from "node:child_process"
import { existsSync } from "node:fs"
import { readFile, realpath, stat } from "node:fs/promises"
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

function resolveRoot(): string {
  const pluginDir = currentPluginDir()
  const candidates = [
    process.env.OPENCODE_SEO_ROOT,
    path.resolve(pluginDir, "../../.."),
    path.resolve(pluginDir, "../../opencode-seo"),
    process.cwd(),
  ].filter((value): value is string => Boolean(value))

  for (const candidate of candidates) {
    if (isRuntimeRoot(candidate)) return candidate
  }

  return candidates[0] ?? process.cwd()
}

function resolveAssetsRoot(runtimeRoot: string): string {
  const pluginDir = currentPluginDir()
  const candidates = [
    runtimeRoot,
    path.resolve(pluginDir, "../.."),
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

function findPython(): PythonCommand | undefined {
  for (const candidate of pythonCandidates()) {
    const result = spawnSync(candidate.command, [...candidate.prefix, "-c", "import sys"], {
      encoding: "utf8",
      timeout: 5_000,
      windowsHide: true,
    })
    if (result.status === 0) return candidate
  }

  return undefined
}

function clip(value: string): string {
  if (Buffer.byteLength(value, "utf8") <= MAX_OUTPUT_BYTES) return value
  return `${value.slice(0, MAX_OUTPUT_BYTES)}\n[output truncated]`
}

function runProcess(
  python: PythonCommand,
  args: string[],
  options: { cwd: string; timeout: number; signal?: AbortSignal },
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

export default Plugin.define({
  id: "opencode-seo",
  async setup(ctx) {
    const runtimeRoot = resolveRoot()
    const assetsRoot = resolveAssetsRoot(runtimeRoot)
    const runtime = path.join(runtimeRoot, "scripts", "runtime.py")

    await ctx.tool.transform((editor) => {
      editor.add({
        name: "seo",
        description:
          "Run the bundled OpenCode SEO Python runtime. Use action run with a script name and arguments, setup or doctor for runtime maintenance, path for the install root, or read for a bundled reference file.",
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
          }

          try {
            const source =
              context.messageID && context.id
                ? { type: "tool" as const, messageID: context.messageID, id: context.id }
                : undefined
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

            if (request.action === "path") {
              return { content: runtimeRoot }
            }

            if (request.action === "read") {
              if (!request.path) throw new Error("action read requires path")
              return { content: await readAsset(runtimeRoot, assetsRoot, request.path) }
            }

            const python = findPython()
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
              cwd: process.cwd(),
              timeout,
              signal: context.signal,
            })

            const output = [result.stdout.trim(), result.stderr.trim()].filter(Boolean).join("\n")
            const prefix = result.timedOut
              ? `ERROR: command timed out after ${timeout} ms`
              : result.code === 0
                ? ""
                : `ERROR: command exited with code ${result.code}`

            return {
              content: [prefix, output].filter(Boolean).join("\n") || "OK",
            }
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
        if (typeof file !== "string" || !/\.(html?|json|md)$/i.test(file)) return
        if (!existsSync(file)) return

        const python = findPython()
        if (!python) return

        const hookScript = path.join(runtimeRoot, "hooks", "validate-schema.py")
        if (!existsSync(hookScript)) return

        const result = await runProcess(python, [hookScript, file], {
          cwd: process.cwd(),
          timeout: 30_000,
        })

        const text = [result.stdout.trim(), result.code === 2 ? result.stderr.trim() : ""]
          .filter(Boolean)
          .join("\n")
          .trim()
        if (!text) return

        event.result = appendToolText(event.result, `[schema validation]\n${text}`) as typeof event.result
      } catch {
        return
      }
    })
  },
})
