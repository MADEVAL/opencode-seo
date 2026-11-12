# OpenCode SEO: план полной поддержки OpenCode V2 с сохранением других harness

Статус: завершено и проверено на OpenCode 2.2.7 (2026-11-12). Фазы 0-10
закрыты, полный `pytest` зеленый, OpenCode видит 26 skills, 19 агентов,
35 команд и локальный plugin.
Цель: сделать OpenCode главным и лучшим образом поддерживаемым harness, не удаляя
поддержку Claude Code, Cursor, Codex, Cline, Aider, Antigravity и других клиентов,
которые читают `AGENTS.md` или `SKILL.md`.

Ключевая формула:

> Один источник контента, отдельная генерация под каждый harness, OpenCode получает
> самый полный и самый нативный слой интеграции.

## Текущий статус

Фаза 0 и Фазы 1-4 выполнены в основной части:

- добавлен `opencode.json` без explicit `skills`, чтобы не перекрыть `.opencode/skills`;
- добавлен plugin `opencode-seo` с инструментом `seo` и schema-хуком;
- добавлены 35 команд `/seo` и `/seo/<sub>`;
- добавлен генератор `scripts/build_opencode.py` с `--check` и `--dist`;
- сгенерированы `.opencode/skills` (26), `.opencode/agents` (19), `.opencode/commands` (35),
  `.opencode/plugins/opencode-seo`;
- OpenCode видит 26 skills и 19 агентов, `opencode plugin list` показывает plugin;
- Claude-слой не изменен, кроме добавления `OPENCODE_SEO_PYTHON` alias в launcher;
- добавлен контрактный тест `tests/test_opencode_generation.py`;
- добавлены `OPENCODE_SEO_DATA_DIR`, `OPENCODE_SEO_CONFIG_DIR`,
  `OPENCODE_SEO_GOOGLE_AUTH`, `OPENCODE_SEO_LOCAL_TARGETS` с fallback на старые имена;
- добавлены launcher-обертки `scripts/opencode-seo` и `scripts/opencode-seo.ps1`;
- runtime `setup --skip-browser` и `run page_checks.py` проверены на реальном HTML;
- в OpenCode-копии `seo` и `seo-audit` добавлен протокол фоновых субагентов:
  параллельный запуск, сбор отчетов, `sessionID`, fallback на inline;
- добавлен `scripts/install_opencode_extension.py` и обертки
  `extensions/install-opencode.sh|ps1`: skills, agents, скрипты расширений,
  `mcp.servers`, маскирование секретов в `--dry-run`, JSONC merge с `.bak`;
- добавлен `docs/OPENCODE-MCP.md` и OpenCode-раздел в `docs/MCP-INTEGRATION.md`;
- добавлены `install-opencode.sh|ps1` и `scripts/install_opencode_package.py`
  с установкой, проверкой и удалением;
- обновлены `README.md`, `docs/INSTALLATION.md`, `docs/OPENCODE-INSTALL.md`;
- версия поднята до `3.0.0` во всех манифестах, skill metadata, установщиках
  и сгенерированном OpenCode-слое;
- добавлен `CHANGELOG` для `3.0.0` и легкий OpenCode CI.

Финальная проверка выполнена: `python scripts/build_opencode.py --check`,
`pytest tests -q` (2372 passed, 33 skipped), `opencode plugin list`,
`opencode debug agents`, `opencode debug config`, установка в чистый каталог
и dry-run расширений. Остался только тег `v3.0.0`.

---

## 0. Зафиксированные решения

1. OpenCode - приоритетный harness. Его поддержка должна быть полнее, чем у остальных.
2. Claude Code и другие harness не удаляются. Их установка, документация и тесты
   сохраняются.
3. Проект переименовывается в OpenCode SEO. Внутренние legacy-имена сохраняются как
   алиасы на время миграции.
4. Модельная политика: у Claude-агентов остается `model: sonnet|opus`, у OpenCode
   агентов модель не задается и наследуется от сессии. Это ответ на вопрос 3 из
   предыдущего обсуждения.
5. Реализуется максимум возможностей актуальной документации OpenCode V2: skills,
   agents, commands, plugins, permissions, MCP, hooks, `AGENTS.md`, CLI-диагностика.

---

## 1. Краткое резюме

Репозиторий содержит:

| Компонент | Количество |
|---|---:|
| Каталоги skills (`skills/*/SKILL.md`) | 26 |
| Агенты (`agents/*.md`) | 19 |
| Python-скрипты (`scripts/*.py`) | 63 |
| Расширения (`extensions/*`) | 9 |
| Markdown-файлы всего | 219 |

Что уже работает и должно сохраниться:

- `skills/` в формате Agent Skills, который читают Claude Code, Cursor, Codex,
  Cline, Aider, Antigravity и OpenCode.
- `AGENTS.md` как общий источник инструкций для не-Claude harness.
- `CLAUDE.md`, `.claude-plugin/`, `hooks/`, `agents/` как Claude-слой.
- Python-рантайм, SSRF-защита, 63 скрипта, 9 расширений.

Что мешает OpenCode:

1. `${CLAUDE_PLUGIN_ROOT}` в десятках markdown-файлов. OpenCode не раскрывает ее ни в
   skill body, ни в system prompt агента.
2. Frontmatter агентов использует Claude-поля: `model: sonnet|opus`, `maxTurns`,
   `tools`. В OpenCode V2 это `model`, `steps`, `permissions`.
3. `user-invocable` и `argument-hint` не создают слэш-команды. Нужен
   `.opencode/commands`.
4. `hooks/hooks.json` и `PostToolUse` не поддерживаются. Нужен plugin hook.
5. `CLAUDE.md` в OpenCode V2 не читается. Нужен `AGENTS.md`.
6. MCP-расширения пишут в `~/.claude.json`. OpenCode читает `mcp.servers` из
   `opencode.json(c)`.
7. `mcp__dataforseo__*` не существует в OpenCode. Нужно `dataforseo_*` или Code Mode.
8. Субагенты OpenCode всегда фоновые, оркестрация аудита должна это учитывать.
9. Установщики и тесты завязаны на `~/.claude`.

Решение:

- Оставить корневые `skills/`, `agents/`, `hooks/`, `.claude-plugin/`, `CLAUDE.md`
  как канонический источник и Claude-слой.
- Добавить генератор `scripts/build_opencode.py`, который собирает отдельный
  OpenCode-таргет в `.opencode/` и `dist/opencode/`.
- Добавить серверный plugin `opencode-seo` с инструментом `seo` и schema-хуком.
- Добавить `/seo` и вложенные команды.
- Переписать установщики так, чтобы они поддерживали
  `--target opencode|claude|generic|all`, по умолчанию `opencode`.
- Переименовать пользовательский бренд, сохранив legacy-алиасы.

Оценка: 18-22 инженерных дня с учетом двух таргетов, генератора, расширений и
тестов на Windows, macOS и Linux.

---

## 2. Документация OpenCode V2 и покрытие возможностей

Использованы только актуальные документы V2:

- https://opencode.ai/docs/llms.txt
- https://opencode.ai/docs/skills/
- https://opencode.ai/docs/agents/
- https://opencode.ai/docs/commands/
- https://opencode.ai/docs/plugins/
- https://opencode.ai/docs/build/plugins/
- https://opencode.ai/docs/build/plugins/server/
- https://opencode.ai/docs/config/
- https://opencode.ai/docs/permissions/
- https://opencode.ai/docs/policies/
- https://opencode.ai/docs/tools/
- https://opencode.ai/docs/mcp-servers/
- https://opencode.ai/docs/instructions/
- https://opencode.ai/docs/cli/commands/

### 2.1 Матрица покрытия

| Возможность OpenCode | Как используется в OpenCode SEO |
|---|---|
| Skills discovery и precedence | `.opencode/skills`, глобально `~/.config/opencode/skills`, отдельный source в `opencode.json` |
| `metadata.opencode/autoinvoke` | Не используется: все 26 skills должны быть видимы. Поле поддерживается, но не требуется |
| Agents `mode: subagent` | Все 19 специалистов |
| Agents `steps` | Замена `maxTurns` |
| Agents `permissions` | Точная копия исходных `tools` |
| Commands `$ARGUMENTS`, `$1`, `$2` | `/seo`, `/seo/audit`, `/seo/drift`; `$ARGUMENTS` используется везде |
| Commands `agent`, `model`, `subagent` | Не используются: команда наследует агента и модель сессии |
| Plugins `ctx.tool.transform` | Инструмент `seo` для Python-рантайма |
| Plugins `ctx.tool.hook` | Валидация JSON-LD после edit/write |
| Plugins `ctx.permission.assert` | Разрешение на запуск скрипта |
| MCP `mcp.servers` | DataForSEO, Firecrawl, Ahrefs, Profound, SE Ranking, Banana |
| MCP `codemode: false` | Прямые имена `dataforseo_*` |
| MCP `timeout` | Долгие SEO-запросы |
| Permissions | Allowlist, `.env` ask, запрет рекурсивных субагентов |
| Policies | Не используются: политики остаются опциональными для enterprise |
| `AGENTS.md` | Главные инструкции проекта и установленного пакета; `instructions` не дублирует его |
| `instructions` config | Не используется: `AGENTS.md` находится автоматически. Значение можно добавить для внешних правил |
| `references` config | Не используется: справки лежат внутри skills и читаются по относительным путям |
| Config `{env:...}` | Ключи MCP и провайдеров без записи секретов |
| Code Mode `execute` | Не используется: SEO MCP-серверы работают с `codemode: false`, а `seo` tool доступен напрямую |
| `experimental.subagent_depth` | Ограничение вложенности |
| `opencode debug agents/config/paths` | Диагностика и тесты |
| `opencode mcp list`, `opencode plugin list` | Проверка установки |
| `opencode run --agent`, `--format json` | CI и smoke-тесты |
| `/reload` | Применение конфигурации без перезапуска |

---

## 3. Матрица несовместимостей

| Концепция | Claude и другие сейчас | OpenCode V2 | Действие |
|---|---|---|---|
| Инструкции проекта | `CLAUDE.md`, `AGENTS.md` | `AGENTS.md` | `AGENTS.md` сделать главным, `CLAUDE.md` оставить для Claude |
| Skills | `~/.claude/skills`, `.claude/skills` | `~/.config/opencode/skills`, `.opencode/skills` | Генерировать OpenCode-копии |
| Агенты | `~/.claude/agents/*.md` | `~/.config/opencode/agents/*.md` | Генерировать OpenCode-версии |
| Вызов skill | Skill tool | `skill` tool, `@skill-id` | Обновить только OpenCode-копии |
| Слэш-команды | `user-invocable`, `argument-hint` | `.opencode/commands/*.md` | Добавить команды |
| Путь плагина | `${CLAUDE_PLUGIN_ROOT}` | нет переменной | Инструмент `seo` в OpenCode, старый путь в Claude |
| Запуск Python | launcher в Claude | plugin tool в OpenCode | Два представления из одного источника |
| Модель агента | `model: sonnet|opus` | наследование или `provider/model` | Claude оставляет, OpenCode наследует |
| Лимит шагов | `maxTurns: 45` | `steps: 45` | Генератор переименовывает |
| Набор инструментов | `tools: Read, Bash, ...` | `permissions` | Генератор конвертирует |
| Субагенты | Agent/Task tool | `subagent`, всегда фон | OpenCode-оркестрация отдельная |
| MCP-инструменты | `mcp__server__tool` | `server_tool` | Генератор переименовывает |
| MCP-конфиг | `~/.claude.json` | `opencode.json`, `mcp.servers` | Два установщика |
| Хуки | `hooks/hooks.json` | plugin `ctx.tool.hook` | Claude-хук и OpenCode-plugin |
| Манифест | `.claude-plugin/plugin.json` | нет прямого аналога | Оставить Claude, добавить `package.json` |
| Данные рантайма | `CLAUDE_PLUGIN_DATA` | нет переменной | `OPENCODE_SEO_DATA_DIR` с fallback |
| Конфиг credentials | `~/.config/claude-seo` | `~/.config/opencode-seo` | Новый путь, старый читается |

---

## 4. Целевая архитектура

### 4.1 Один источник, два основных таргета

```text
opencode-seo/
  AGENTS.md                         # главные инструкции, OpenCode первым
  CLAUDE.md                         # Claude-инструкции, сохраняются
  README.md                         # OpenCode SEO, все harness
  skills/                           # канонические skills, Claude-совместимые
    seo/SKILL.md
    seo/references/
    seo-*/SKILL.md
  agents/                           # канонические Claude-агенты
    seo-technical.md
    ...
  hooks/                            # Claude hooks, сохраняются
    hooks.json
    validate-schema.py
  .claude-plugin/                   # Claude manifest, сохраняется
    plugin.json
    marketplace.json
  opencode/                         # OpenCode-исходники
    plugin/
      opencode-seo/
        index.ts                    # tool `seo` + schema hook
    commands/
      seo.md
      seo/
        audit.md
        page.md
        ...
    opencode.json                   # шаблон конфига
  scripts/
    build_opencode.py               # генератор OpenCode-таргета
    sync_opencode_layout.py         # проверка/generate для разработки
    opencode-seo                    # новый launcher (Unix)
    opencode-seo.ps1                # новый launcher (Windows)
    claude-seo                      # legacy alias
    runtime.py
    ...
  .opencode/                        # сгенерированный OpenCode-таргет, коммитится
    skills/
    agents/
    commands/
    plugins/
  dist/
    opencode/                       # install payload
    claude/                         # install payload
    generic/                        # skills + AGENTS.md
  extensions/
  tests/
  docs/
```

Почему `.opencode/` коммитится:

- OpenCode в режиме проекта читает `.opencode/skills`, `.opencode/agents`,
  `.opencode/commands`, `.opencode/plugins` автоматически.
- Пользователь может клонировать репозиторий и сразу работать без сборки.
- CI проверяет, что сгенерированный слой совпадает с каноническим.

Важно: не добавлять `./skills` в `skills` config. Канонический `skills/` содержит
Claude-вызовы. Explicit source в `opencode.json` имеет более высокий приоритет, чем
`.opencode/skills`, и перекрыл бы OpenCode-версии. OpenCode должен читать только
`.opencode/skills` (автодискавери) или `./.opencode/skills`, если нужен явный source.

Почему `dist/` нужен:

- Глобальный установщик не должен копировать весь репозиторий.
- `dist/opencode` содержит только OpenCode-артефакты.
- `dist/claude` сохраняет текущий формат и поведение.
- `dist/generic` содержит skills и `AGENTS.md` для остальных harness.

### 4.2 Глобальная установка OpenCode

```text
~/.config/opencode/
  opencode.json                     # рекомендуется
  skills/
    seo/
    seo-agentic/
    ...
  agents/
    seo-technical.md
    ...
  commands/
    seo.md
    seo/
      audit.md
      ...
  plugins/
    opencode-seo/
      index.ts
  opencode-seo/                     # install root для Python-рантайма
    scripts/
    requirements.txt
    data/
    schema/
    pyproject.toml
    .opencode-seo-root
```

### 4.3 Глобальная установка Claude и других

```text
~/.claude/
  skills/seo/...                    # как сейчас
  agents/seo-*.md                   # как сейчас
  settings.json                     # hooks, если включены
```

Для Cursor, Codex, Cline, Aider, Antigravity:

- `skills/` копируется в выбранный каталог harness.
- `AGENTS.md` остается общим источником.
- Никаких OpenCode-специфичных полей в generic-таргете нет.

### 4.4 Поток выполнения в OpenCode

```text
/seo audit https://example.com
  -> command seo.md подставляет $ARGUMENTS
  -> агент загружает skill seo
  -> skill вызывает seo({action:"run", script:"render_page.py", ...})
  -> plugin находит runtime.py, запускает Python без shell
  -> runtime.py использует venv и возвращает JSON
  -> агент запускает субагентов
  -> субагенты пишут findings, родитель собирает отчет
  -> plugin hook проверяет JSON-LD после edit/write
```

---

## 5. Проектные решения (ADR)

### 5.0 Рассмотренные варианты

| Вариант | Плюсы | Минусы | Вердикт |
|---|---|---|---|
| A. OpenCode-only | Просто, нет legacy | Нарушает требование сохранить другие harness | Отклонено |
| B. Две ручные копии skills/agents | Прозрачно | Дрейф, двойная правка, 19+26 файлов | Отклонено |
| C. Генератор из одного источника | Один контент, разные frontmatter и команды | Нужен build-step и CI | Выбран |
| D. Только runtime-абстракция | Нет дублирования | Не решает frontmatter, команды, хуки, MCP | Недостаточно |
| E. Переписать Python на TypeScript | Нативно | Огромный объем, потеря проверенного кода | Отклонено |

Для команд:

| Вариант | Плюсы | Минусы | Вердикт |
|---|---|---|---|
| Один `/seo` с `$ARGUMENTS` | Привычный UX | Нет отдельных описаний | Обязателен |
| 33 отдельные команды | Discoverability | Дублирование | Дополнительно |
| `/seo/<sub>` вложенные команды | Нативно | Другая форма ввода | Основной |

Для MCP:

| Вариант | Плюсы | Минусы | Вердикт |
|---|---|---|---|
| Code Mode по умолчанию | Нативно, экономит контекст | Нужно переписать вызовы | Альтернатива |
| `codemode: false` | Имена `server_tool`, проще permissions | Больше инструментов в контексте | Выбран для SEO-серверов |

### ADR-1. Рантайм через plugin-инструмент `seo`

В OpenCode добавить инструмент:

```jsonc
seo({ "action": "run", "script": "page_checks.py", "args": ["--url", "https://example.com"] })
seo({ "action": "setup" })
seo({ "action": "doctor" })
seo({ "action": "path" })
seo({ "action": "read", "path": "skills/seo/references/quality-gates.md" })
```

Почему:

- OpenCode не раскрывает `${CLAUDE_PLUGIN_ROOT}`.
- Абсолютные пути ломаются при переносе и обновлении.
- Shell-вызовы различаются в bash и PowerShell.
- Один инструмент централизует таймауты, ошибки, permissions и JSON-вывод.

Реализация:

- `resolveRoot()` ищет `OPENCODE_SEO_ROOT`, `ctx.options.root`, соседний
  `opencode-seo`, корень репозитория, workspace.
- `findPython()` ищет `OPENCODE_SEO_PYTHON`, `CLAUDE_SEO_PYTHON`, затем `py -3`,
  `python3`, `python`, версионные интерпретаторы.
- `spawn` без `shell: true`, аргументы массивом, `cwd` = workspace.
- `run` вызывает `python runtime.py run <script> ...args`.
- `setup` и `doctor` вызывают соответствующие команды runtime.
- Перед запуском `ctx.permission.assert({ action: "seo", resources: [script] })`.
- `run` принимает только имя скрипта, не путь. `runtime.py` уже содержит allowlist
  `ALLOWED_CORE_SCRIPTS`.
- `read` разрешает только относительные пути внутри install root, отклоняет `..`,
  абсолютные пути, symlink наружу и большие файлы.
- `path` не раскрывает переменные окружения и не читает файлы.

Claude-слой продолжает использовать `"${CLAUDE_PLUGIN_ROOT}/scripts/claude-seo" run`
без изменений.

### ADR-2. Разрешения OpenCode-агентов вместо `tools`

Для каждого OpenCode-агента генератор строит `permissions` из канонического
`tools`. Пример для `seo-technical` (Read, Bash, Write, Glob, Grep):

```yaml
---
description: Technical SEO specialist. Analyzes crawlability, indexability, security, URL structure, mobile optimization, Core Web Vitals, and JavaScript rendering.
mode: subagent
steps: 45
permissions:
  - action: "*"
    resource: "*"
    effect: deny
  - action: read
    resource: "*"
    effect: allow
  - action: glob
    resource: "*"
    effect: allow
  - action: grep
    resource: "*"
    effect: allow
  - action: shell
    resource: "*"
    effect: allow
  - action: edit
    resource: "*"
    effect: allow
  - action: skill
    resource: "seo*"
    effect: allow
  - action: question
    resource: "*"
    effect: allow
  - action: read
    resource: "*.env"
    effect: ask
  - action: read
    resource: "*.env.*"
    effect: ask
  - action: read
    resource: "*.env.example"
    effect: allow
---
```

Правила:

- `deny *` обязателен, иначе базовые разрешения OpenCode разрешают все инструменты.
- `.env`-правила идут последними, чтобы унаследованный `read *` не отменил `ask`.
- `edit` покрывает `write`, `edit`, `patch`.
- `mcp__dataforseo__*` превращается в `dataforseo_*` при `codemode: false`.
- `subagent` запрещен всем специалистам.
- `execute` запрещен специалистам, если MCP работает с `codemode: false`.
- `question` разрешен всем, кто задает уточняющие вопросы.

Таблица соответствия:

| Claude | OpenCode permission |
|---|---|
| Read | `read` |
| Write, Edit | `edit` |
| Bash | `shell` |
| Glob | `glob` |
| Grep | `grep` |
| WebFetch | `webfetch` |
| WebSearch | `websearch` |
| Task / Agent | `subagent` |
| Skill | `skill` |
| AskUserQuestion | `question` |
| `mcp__dataforseo__*` | `dataforseo_*` |
| `mcp__firecrawl__*` | `firecrawl_*` |

### ADR-3. Модельная политика, разъяснение вопроса 3

Вопрос 3 был про то, как назначать модели агентам в OpenCode. Решение:

- Claude-таргет сохраняет `model: sonnet` и `model: opus`, как сейчас.
- OpenCode-таргет не задает `model` вообще. Субагент наследует модель родительской
  сессии. Это работает с любым провайдером: Anthropic, OpenAI, Google, DeepSeek,
  локальные модели.
- Если пользователь хочет зафиксировать модель, он задает ее в `opencode.json`:

```jsonc
{
  "agents": {
    "seo-content": { "model": "anthropic/claude-sonnet-5-5#high" },
    "seo-sxo": { "model": "openai/gpt-6.1-sol#high" }
  }
}
```

Почему так: жесткий `model: sonnet` в OpenCode требует `provider/model` и ломает
пользователей не на Anthropic. Наследование дает предсказуемый выбор и не требует
настройки.

### ADR-4. Слэш-команды

`.opencode/commands/seo.md`:

```md
---
description: SEO audit, page analysis, schema, sitemap, GEO, local, backlinks, and more
---

Load the `seo` skill. Treat the first token of the arguments as the subcommand
and the rest as its arguments. If no subcommand is given, show the command table.

Arguments: $ARGUMENTS
```

`.opencode/commands/seo/audit.md`:

```md
---
description: Full website SEO audit with parallel specialist subagents
---

Load the `seo-audit` skill and run a full audit for: $ARGUMENTS
```

Список команд: `audit`, `page`, `technical`, `content`, `content-brief`, `schema`,
`sitemap`, `images`, `geo`, `agentic`, `plan`, `cluster`, `sxo`, `drift`, `ecommerce`,
`hreflang`, `local`, `maps`, `google`, `backlinks`, `programmatic`,
`competitor-pages`, `flow`, `dataforseo`, `image-gen`, `firecrawl`, `ahrefs`,
`seranking`, `profound`, `bing`, `matomo`, `unlighthouse`, `setup`, `doctor`.

Claude-таргет продолжает использовать `user-invocable` и `argument-hint`.

### ADR-5. Субагенты и параллельность

- Вызов: `subagent({ agent: "seo-technical", description: "...", prompt: "..." })`.
- Несколько вызовов в одном шаге дают параллельный запуск.
- Родитель получает `<subagent>` сообщение при простое ребенка.
- Для продолжения использовать `sessionID`.
- `experimental.subagent_depth` оставить `1`.
- В `seo-audit` заменить "spawn and wait" на "launch all, continue collecting,
  merge partial findings".
- Каждый субагент пишет partial `findings/*.md` после первого прохода.

Claude-таргет сохраняет текущую синхронную модель делегирования.

### ADR-6. Хуки через plugin

OpenCode-хук:

```ts
await ctx.tool.hook("execute.after", async (event) => {
  if (event.status !== "completed") return
  if (!["write", "edit", "patch"].includes(event.tool)) return
  const file = event.input?.path
  if (!file || !/\.(html?|json|md)$/i.test(file)) return
  const out = await runHookPython("hooks/validate-schema.py", [file])
  if (out.code === 2 || out.stdout.trim()) {
    event.result = appendText(event.result, formatHookOutput(out))
  }
})
```

Примечание для реализации: точный тип `ToolExecuteCompleted` проверяется по
`@opencode/plugin` в момент написания кода. Если `execute.after` не содержит `input`,
путь запоминается в `execute.before` по идентификатору вызова.

Claude-таргет сохраняет `hooks/hooks.json` и `PostToolUse`.

### ADR-7. MCP и Code Mode

OpenCode-конфиг:

```jsonc
{
  "mcp": {
    "servers": {
      "dataforseo": {
        "type": "local",
        "command": ["npx", "-y", "dataforseo-mcp-server@2.8.10"],
        "environment": {
          "DATAFORSEO_USERNAME": "{env:DATAFORSEO_USERNAME}",
          "DATAFORSEO_PASSWORD": "{env:DATAFORSEO_PASSWORD}",
          "ENABLED_MODULES": "SERP,KEYWORDS_DATA,ONPAGE,DATAFORSEO_LABS,BACKLINKS,DOMAIN_ANALYTICS,BUSINESS_DATA,CONTENT_ANALYSIS,AI_OPTIMIZATION"
        },
        "codemode": false,
        "timeout": { "execution": 600000 }
      }
    }
  }
}
```

Почему `codemode: false`:

- Имена становятся `dataforseo_serp_organic_live_advanced`, ближе к текущим промптам.
- Не нужно разрешать `execute` каждому агенту.
- Проще permissions: `{ "action": "dataforseo_*", "resource": "*" }`.

Альтернатива: Code Mode и вызовы `tools.dataforseo.serp_organic_live_advanced(...)`.

Таблица расширений:

| Расширение | Сервер | Тип | Примечание |
|---|---|---|---|
| dataforseo | `dataforseo` | local | npx, env |
| firecrawl | `firecrawl-mcp` | local | `FIRECRAWL_API_KEY` |
| ahrefs | `ahrefs` | remote/local | bearer token |
| profound | `profound` | remote | API key |
| seranking | `seranking` | remote | API key |
| banana | `nanobanana-mcp` | local | Gemini key |
| bing-webmaster | нет MCP | - | ключ в конфиг |
| matomo | нет MCP | - | URL и token |
| unlighthouse | нет MCP | - | локальный runner |

Claude-таргет продолжает писать `mcpServers` в `~/.claude.json`.

### ADR-8. Каталоги данных и переменные окружения

| Назначение | Новое имя | Fallback |
|---|---|---|
| Корень установки | `OPENCODE_SEO_ROOT` | `CLAUDE_PLUGIN_ROOT` |
| Python | `OPENCODE_SEO_PYTHON` | `CLAUDE_SEO_PYTHON` |
| Данные рантайма | `OPENCODE_SEO_DATA_DIR` | `CLAUDE_SEO_DATA_DIR`, `CLAUDE_PLUGIN_DATA` |
| Конфиг credentials | `OPENCODE_SEO_CONFIG_DIR` | `CLAUDE_SEO_CONFIG_DIR` |
| Тестовые локальные цели | `OPENCODE_SEO_LOCAL_TARGETS` | `CLAUDE_SEO_LOCAL_TARGETS` |
| Google auth mode | `OPENCODE_SEO_GOOGLE_AUTH` | `CLAUDE_SEO_GOOGLE_AUTH` |

Пути:

- OpenCode credentials: `~/.config/opencode-seo/`.
- Claude credentials: `~/.config/claude-seo/` остается.
- При первом запуске OpenCode читает старый путь, если нового нет.
- Рантайм OpenCode: `%LOCALAPPDATA%\opencode-seo` или
  `$XDG_DATA_HOME/opencode-seo`.
- `runtime.py` определяет plugin-режим по маркеру `.opencode-seo-root`,
  `opencode.json` или env, а не только по `.claude-plugin/plugin.json`.

### ADR-9. Мульти-harness, переименование и алиасы

Решение: OpenCode SEO - новое имя продукта. Claude-слой сохраняется.

| Старое | Новое | Алиас |
|---|---|---|
| Claude SEO (бренд) | OpenCode SEO | В README указать происхождение |
| `claude-seo` launcher | `opencode-seo` | `claude-seo` остается symlink/скриптом |
| plugin id `claude-seo` | `opencode-seo` | Claude manifest сохраняет `claude-seo` |
| `CLAUDE_SEO_*` | `OPENCODE_SEO_*` | старые читаются |
| `~/.config/claude-seo` | `~/.config/opencode-seo` | старый читается |
| `CLAUDE_PLUGIN_DATA` | `OPENCODE_SEO_DATA_DIR` | старый читается |
| Skill ID `seo`, `seo-*` | без изменений | нет |
| `CLAUDE.md` | без изменений для Claude | OpenCode использует `AGENTS.md` |
| `.claude-plugin/plugin.json` | без изменений | нужен для Claude marketplace |
| `hooks/hooks.json` | без изменений | OpenCode использует plugin |

Правила:

- Не переименовывать skill ID: это ломает ссылки и `@seo`.
- Не переименовывать `.claude-plugin` внутри Claude-манифеста: это ломает установку.
- Переименовать README, docs, install-сообщения, package name, repo description.
- Версия `3.0.0`, потому что меняется структура установки и добавляется генератор.
- В `CHANGELOG` явно указать: OpenCode support added, Claude support retained.

---

## 6. Пошаговый план

### Фаза 0. Решения и baseline (0.5 дня)

1. Создать ветку `feat/opencode-v2`.
2. Зафиксировать baseline: `python -m pytest tests/ -q`, записать число тестов.
3. Утвердить rename map из ADR-9.
4. Проверить, что текущая установка Claude работает, чтобы позже сравнивать.
5. Создать этот документ.

Критерий: baseline зеленый, rename map зафиксирован.

### Фаза 1. Каркас и генератор (1.5 дня)

1. Создать `opencode/plugin/opencode-seo/index.ts`.
2. Создать `opencode/commands/seo.md` и `opencode/commands/seo/*.md`.
3. Создать `opencode/opencode.json` как шаблон.
4. Создать `scripts/build_opencode.py`:
   - читает `skills/`, `agents/`, `scripts/`, `data/`, `schema/`;
   - генерирует `.opencode/skills`, `.opencode/agents`, `.opencode/commands`,
     `.opencode/plugins`;
   - генерирует `dist/opencode`, `dist/claude`, `dist/generic`;
   - поддерживает `--check`.
5. Создать `scripts/sync_opencode_layout.py` для разработки.
6. Добавить `opencode.json` в корень с `instructions`, `permissions`,
   `experimental.subagent_depth`. Не указывать `skills: ["./skills"]`: это
   канонический Claude-слой, и explicit source имеет более высокий приоритет,
   чем `.opencode/skills`, поэтому Claude-версии перекрыли бы OpenCode-версии.
   Если нужен явный source, указывать `./.opencode/skills`.

Критерий:

- `python scripts/build_opencode.py --check` зеленый.
- `opencode debug agents` показывает 19 OpenCode-агентов.
- `opencode` видит `/seo`.
- Claude-артефакты не изменились.

### Фаза 2. Рантайм-мост (2 дня)

1. Реализовать `seo` tool: `run`, `setup`, `doctor`, `path`, `read`.
2. Реализовать поиск Python и install root.
3. Добавить `ctx.permission.assert`.
4. Добавить таймауты, отмену по `context.signal`, лимит вывода.
5. Добавить обработку ошибок.
6. Добавить `OPENCODE_SEO_DATA_DIR` в `runtime.py` и fallback.
7. Обновить `runtime.py`: `_is_plugin`, `_plugin_version`, env aliases.
8. Добавить `scripts/opencode-seo` и `scripts/opencode-seo.ps1`.

Критерий:

- `seo({action:"doctor"})` возвращает JSON без абсолютных путей.
- `seo({action:"run", script:"page_checks.py", args:["--url","https://example.com"]})`
  возвращает JSON.
- Windows и Unix работают без bash.
- Claude launcher продолжает работать.

### Фаза 3. Генерация OpenCode skills (2 дня)

1. Генератор копирует 26 skills в `.opencode/skills`.
2. В копиях заменяет:
   - `"${CLAUDE_PLUGIN_ROOT}/scripts/claude-seo" run X` на вызов `seo` tool;
   - `${CLAUDE_PLUGIN_ROOT}/skills/...` на относительные пути или `seo read`;
   - `WebFetch`/`WebSearch` на `webfetch`/`websearch`;
   - `/seo ...` на актуальные команды OpenCode.
3. Удаляет или игнорирует `user-invocable` и `argument-hint` в OpenCode-копиях.
4. Сохраняет `name`, `description`, `license`, `metadata`.
5. Для extension-зеркал делает то же.
6. Добавляет проверку, что относительные ссылки существуют.

Критерий:

- В `.opencode/skills` нет `${CLAUDE_PLUGIN_ROOT}`.
- Все 26 skills находятся OpenCode.
- Корневые `skills/` не изменены по смыслу и продолжают работать в Claude.
- `python scripts/build_opencode.py --check` зеленый.

### Фаза 4. Генерация OpenCode agents (2 дня)

1. Генератор читает 19 `agents/*.md`.
2. Строит OpenCode-frontmatter:
   - `mode: subagent`;
   - `steps` из `maxTurns`;
   - `permissions` из `tools`;
   - удаляет `model`, `name`;
   - добавляет `question`, `.env`-правила, запрет `subagent`.
3. В теле заменяет launcher и MCP-имена.
4. Генерирует агентов расширений.
5. Добавляет `tests/test_opencode_agent_generation.py`.

Критерий:

- 19 агентов имеют `mode: subagent`.
- Нет `maxTurns`, `tools:`, `model: sonnet`, `mcp__`.
- Permission-матрица совпадает с исходными `tools`.
- Claude-агенты не изменились.

### Фаза 5. Оркестрация (1 день)

1. В OpenCode-копии `seo` и `seo-audit` описать фоновые субагенты и сбор результатов.
2. Сохранить partial findings.
3. Проверить условные ветки: Google, Matomo, backlinks, local, maps, ecommerce,
   drift, cluster.
4. Добавить fallback: если субагент недоступен, выполнять inline.
5. Claude-копии не менять.

Критерий:

- Пробный аудит запускает минимум 3 субагента параллельно.
- Родитель собирает единый отчет.
- При обрыве одного субагента остальные результаты сохраняются.

### Фаза 6. Команды (1 день)

1. `/seo` с `$ARGUMENTS`.
2. `/seo/<sub>` для всех подкоманд.
3. `/seo/setup`, `/seo/doctor`.
4. Проверить `$1` и `$2` для `drift`, `maps`, `google`.
5. Добавить команды в `dist/opencode`.

Критерий:

- Все команды видны в OpenCode.
- Аргументы с пробелами и кавычками передаются корректно.
- Claude-команды не затронуты.

### Фаза 7. Хуки и безопасность (1 день)

1. Реализовать `execute.after` hook.
2. Проверить `write`, `edit`, `patch`.
3. Запускать `validate-schema.py` тем же Python-резолвером.
4. Добавить результат в `event.result` без потери исходного вывода.
5. Не запускать хук для бинарных и неподдерживаемых файлов.
6. Добавить тесты: валидный JSON-LD, placeholder, deprecated type, warning-only.
7. Проверить, что fetched content недоверенный.
8. Проверить, что plugin не логирует секреты.

Критерий:

- Правка HTML с `[Business Name]` в JSON-LD возвращает предупреждение.
- Правка обычного `.py` не запускает Python-хук.
- Ошибка Python не ломает запись.
- Claude hook продолжает работать.

### Фаза 8. Расширения и MCP для двух таргетов (3 дня)

1. Переписать 9 установщиков:
   - `--target opencode|claude|all`, по умолчанию `opencode`;
   - OpenCode: `~/.config/opencode/{skills,agents,commands,plugins}` и
     `mcp.servers`;
   - Claude: текущие `~/.claude` и `~/.claude.json`;
   - атомарная запись, сохранение существующего JSON;
   - права 0600 на Unix, ACL на Windows;
   - проверка `opencode mcp list` и `claude` smoke.
2. Для dataforseo, firecrawl, ahrefs, profound, seranking, banana:
   - `type: local|remote`;
   - `codemode: false`;
   - `timeout.execution`;
   - env-переменные.
3. Для bing-webmaster и matomo: ключи в конфиг, без MCP.
4. Обновить skills и agents расширений в обоих таргетах.
5. Обновить документацию расширений.

Критерий:

- `opencode mcp list` показывает серверы.
- Инструменты доступны как `dataforseo_*`, `firecrawl_*`.
- Claude MCP продолжает работать.
- Повторная установка идемпотентна.
- Секреты не попадают в git и логи.

### Фаза 9. Документация и установка (2 дня)

1. `AGENTS.md`: OpenCode первым, затем остальные harness.
2. `CLAUDE.md`: сохранить и обновить ссылки на новый бренд.
3. `README.md`: OpenCode SEO, установка OpenCode, затем Claude и другие.
4. `docs/INSTALLATION.md`, `COMMANDS.md`, `MCP-INTEGRATION.md`,
   `TROUBLESHOOTING.md`, `ARCHITECTURE.md`.
5. `install.sh` и `install.ps1`:
   - `--target` с дефолтом `opencode`;
   - копирование `dist/*`;
   - создание `.opencode-seo-root`;
   - миграция `~/.claude` и `~/.config/claude-seo`;
   - smoke checks.
6. `uninstall.sh` и `uninstall.ps1`.
7. `.gitignore`: `dist/`, `.opencode-seo-root`, venv, но `.opencode` коммитится.

Критерий:

- Чистая установка OpenCode на Windows и Linux/macOS.
- Чистая установка Claude не сломана.
- `/seo doctor` работает.
- В OpenCode-инструкциях нет `~/.claude`.

### Фаза 10. Тесты, CI и релиз (2 дня)

1. Сохранить существующие Claude-тесты.
2. Обновить тесты, которые проверяют layout, hooks, manifest, portability.
3. Добавить:
   - `test_build_opencode.py`;
   - `test_opencode_layout.py`;
   - `test_opencode_frontmatter.py`;
   - `test_opencode_commands.py`;
   - `test_opencode_permissions.py`;
   - `test_opencode_mcp_config.py`;
   - `test_opencode_plugin_contract.py`;
   - `test_no_claude_tokens_in_opencode.py`;
   - `test_rename_aliases.py`.
4. CI: Windows, Ubuntu, macOS; Python 3.11-3.14.
5. Smoke:
   - `opencode debug agents`;
   - `opencode debug config`;
   - `opencode mcp list`;
   - `/seo doctor`;
   - `/seo/audit`;
   - Claude smoke.
6. Обновить `CHANGELOG.md`, версию `3.0.0`, `pyproject.toml`, `package.json`.

Критерий: все проверки из раздела 9 зеленые.

---

## 7. Правила генератора

Генератор должен быть идемпотентным и запускаться с `--check` в CI.

### 7.1 Skills

| Что искать | На что менять в OpenCode |
|---|---|
| `"${CLAUDE_PLUGIN_ROOT}/scripts/claude-seo" run X.py` | `seo({ action: "run", script: "X.py", args: [...] })` |
| `${CLAUDE_PLUGIN_ROOT}/skills/` | относительный путь или `seo({action:"read", path:"..."})` |
| `${CLAUDE_PLUGIN_ROOT}/hooks/` | `hooks/` относительно install root |
| `~/.claude/skills` | `~/.config/opencode/skills` |
| `~/.claude/agents` | `~/.config/opencode/agents` |
| `CLAUDE_PLUGIN_ROOT` | удалить |
| `WebFetch` | `webfetch` |
| `WebSearch` | `websearch` |
| `user-invocable` | удалить |
| `argument-hint` | удалить |

### 7.2 Agents

| Что искать | На что менять в OpenCode |
|---|---|
| `model: sonnet` / `model: opus` | удалить строку |
| `maxTurns:` | `steps:` |
| `tools:` | `permissions:` по таблице |
| `mcp__([a-z0-9]+)__([a-z0-9_]+)` | `$1_$2` |
| `Task tool` / `Agent tool` | `subagent` tool |
| `Bash tool` | `shell` tool |
| `Read/Write/Edit tool` | `read`/`edit` tool |

### 7.3 Ограничения

- Не менять корневые `skills/`, `agents/`, `hooks/`, `CLAUDE.md`.
- Не менять исторические записи `CHANGELOG`.
- Не трогать `skills/seo-flow/references/prompts/**` (hash-locked).
- Не менять test fixtures, где старые имена нужны для регрессии.
- Не делать слепую замену слов `read`, `write`, `edit`, `bash` в обычной речи.
- После каждой фазы запускать `--check`.

---

## 8. Точный список файлов

### 8.1 Канонические skills (26)

`skills/seo`, `seo-agentic`, `seo-audit`, `seo-backlinks`, `seo-cluster`,
`seo-competitor-pages`, `seo-content`, `seo-content-brief`, `seo-dataforseo`,
`seo-drift`, `seo-ecommerce`, `seo-flow`, `seo-geo`, `seo-google`, `seo-hreflang`,
`seo-image-gen`, `seo-images`, `seo-local`, `seo-maps`, `seo-page`, `seo-plan`,
`seo-programmatic`, `seo-schema`, `seo-sitemap`, `seo-sxo`, `seo-technical`.

Для каждого: исходник не трогаем, генерируем OpenCode-копию с заменой вызовов,
путей и имен инструментов.

### 8.2 Канонические agents (19)

`seo-technical`, `seo-content`, `seo-schema`, `seo-sitemap`, `seo-performance`,
`seo-visual`, `seo-geo`, `seo-agentic`, `seo-local`, `seo-maps`, `seo-google`,
`seo-backlinks`, `seo-dataforseo`, `seo-image-gen`, `seo-cluster`, `seo-sxo`,
`seo-drift`, `seo-ecommerce`, `seo-flow`.

Для каждого: исходник не трогаем, генерируем OpenCode-версию с `mode`, `steps`,
`permissions` и новыми вызовами.

### 8.3 Extensions (9)

`ahrefs`, `banana`, `bing-webmaster`, `dataforseo`, `firecrawl`, `matomo`,
`profound`, `seranking`, `unlighthouse`.

Для каждого: два установщика, два набора skills/agents, две ветки MCP-конфига.

### 8.4 Корневые файлы

| Файл | Действие |
|---|---|
| `AGENTS.md` | OpenCode первым, другие harness сохранить |
| `CLAUDE.md` | Сохранить, обновить бренд |
| `README.md` | OpenCode SEO, все harness |
| `install.sh` | `--target`, OpenCode по умолчанию, Claude сохранить |
| `install.ps1` | То же для Windows |
| `uninstall.sh` | Удаление выбранного таргета |
| `uninstall.ps1` | То же |
| `pyproject.toml` | version 3.0.0 |
| `package.json` | Новый, для plugin |
| `opencode.json` | Новый, project config |
| `.gitignore` | `dist/`, `.opencode-seo-root` |
| `.claude-plugin/*` | Сохранить для Claude |

---

## 9. Тесты и проверки

### 9.1 Статические проверки OpenCode

- `rg "CLAUDE_PLUGIN_ROOT"` по `.opencode/` не находит совпадений.
- `rg "maxTurns|^tools:|model: (sonnet|opus)"` по `.opencode/agents` не находит.
- `rg "mcp__"` по `.opencode/skills` и `.opencode/agents` не находит.
- Все `.opencode/skills/*/SKILL.md` имеют `name` и `description`.
- Все `.opencode/agents/*.md` имеют `mode: subagent`, `description`, `permissions`.
- Все `.opencode/commands/**/*.md` имеют `description`.
- Нет em dash (существующий house-style тест).

### 9.2 Регрессия Claude и других harness

- Существующие `tests/` зеленые.
- `~/.claude/skills/seo` установка работает.
- `hooks/hooks.json` не изменен.
- `CLAUDE.md` читается Claude.
- `AGENTS.md` читается Cursor, Codex, Cline, Aider, Antigravity.

### 9.3 Новые тесты

```text
tests/test_build_opencode.py
tests/test_opencode_layout.py
tests/test_opencode_frontmatter.py
tests/test_opencode_commands.py
tests/test_opencode_permissions.py
tests/test_opencode_mcp_config.py
tests/test_opencode_plugin_contract.py
tests/test_no_claude_tokens_in_opencode.py
tests/test_rename_aliases.py
```

Проверки:

- генератор идемпотентен;
- `.opencode` совпадает с `dist/opencode`;
- frontmatter допустим;
- permission-матрица совпадает с исходной;
- MCP-конфиг содержит `mcp.servers`, а не `mcpServers`;
- plugin содержит `Plugin.define`, `tool.transform`, `tool.hook`;
- legacy-алиасы работают.

### 9.4 Smoke-тест OpenCode

```bash
opencode --version
opencode debug agents
opencode debug config
opencode mcp list
opencode plugin list
opencode run "List the seo skills you can load"
opencode run --agent seo-technical "Audit https://example.com and return findings"
opencode run --format json --agent seo-page "Analyze https://example.com"
```

В TUI:

```text
/seo doctor
/seo/audit https://example.com
@seo
```

### 9.5 Definition of Done

- [ ] 26 skills найдены OpenCode.
- [ ] 19 агентов найдены и имеют `mode: subagent`.
- [ ] `/seo` и все субкоманды работают.
- [ ] `seo` tool запускает все 63 скрипта через allowlist.
- [ ] Schema hook работает после edit/write.
- [ ] MCP-расширения видны в `opencode mcp list`.
- [ ] Нет `${CLAUDE_PLUGIN_ROOT}`, `maxTurns`, `tools:`, `mcp__` в `.opencode`.
- [ ] `pytest` зеленый на Windows, Ubuntu, macOS.
- [ ] Чистая установка и удаление OpenCode.
- [ ] Чистая установка Claude не сломана.
- [ ] Другие harness читают `AGENTS.md` и `skills/`.
- [ ] README и docs используют OpenCode SEO.
- [ ] Алиасы `claude-seo`, `CLAUDE_SEO_*`, `~/.config/claude-seo` работают.
- [ ] Секреты не логируются и не коммитятся.

---

## 10. Риски и меры

| Риск | Вероятность | Влияние | Мера |
|---|---:|---:|---|
| Дрейф между каноническими и сгенерированными файлами | Высокая | Высокое | `--check` в CI, генератор как единственный путь |
| Ошибка генератора ломает Claude | Средняя | Высокое | `dist/claude` собирается копированием без трансформаций, генератор не меняет корневые файлы |
| Plugin API V2 изменится | Средняя | Высокое | Изолировать в одном файле, fallback на относительные пути |
| Фоновые субагенты завершаются после ответа | Средняя | Высокое | Ждать уведомления, писать partial findings |
| Слишком много субагентов | Средняя | Среднее | Ограничить 8-10 параллельных |
| Windows: Python не найден, путь с пробелами | Высокая | Высокое | Резолвер, `spawn` без shell, тест на пути с пробелами |
| Потеря credentials при миграции | Средняя | Высокое | Fallback на старый путь, не удалять старый конфиг |
| Ослабление permissions | Средняя | Высокое | `deny *` + allowlist, env-правила, тест матрицы |
| MCP Code Mode ломает промпты | Высокая | Среднее | `codemode: false` |
| Переименование ломает ссылки | Высокая | Среднее | Алиасы, редиректы в docs, тесты |
| Дублирование docs для двух harness | Средняя | Низкое | Один README с секциями, `AGENTS.md` как общий |

---

## 11. Порядок PR

1. PR 1: rename map, каркас, генератор skeleton, OpenCode plugin skeleton.
2. PR 2: runtime bridge, `seo` tool, env aliases.
3. PR 3: генерация skills.
4. PR 4: генерация agents.
5. PR 5: orchestration.
6. PR 6: commands.
7. PR 7: hooks.
8. PR 8: extensions и MCP для двух таргетов.
9. PR 9: docs, installers, uninstallers.
10. PR 10: tests, CI, release 3.0.0.

Каждый PR должен оставлять оба таргета рабочими.

---

## 12. Минимальный путь за 3-4 дня

1. Добавить plugin с инструментом `seo`.
2. Сгенерировать 19 OpenCode-агентов из текущих.
3. Добавить `/seo` и `/seo/audit`.
4. Сгенерировать OpenCode-копии `seo`, `seo-audit`, `seo-page`.
5. Проверить `/seo/audit` на одном сайте.

Этого достаточно, чтобы главный сценарий заработал. Остальные skills и расширения
переводить постепенно, не ломая Claude и другие harness.
