# Target Agent Integration Matrix

This document tracks config-only target integration candidates from
[`deepseek-ai/awesome-deepseek-agent`](https://github.com/deepseek-ai/awesome-deepseek-agent).
The rule for this pass is strict:
prefer `PromptCLIRunner` and target YAML/model templates; do not add framework
Python. Image-local wrapper scripts are allowed only when they are target-owned
launch glue and have a reproducible noninteractive runtime contract.

## Integration Status

| Agent | Status | OpenART action | Probe notes |
|---|---|---|---|
| Aider | Active recommended | Add `target.aider.yaml` | Official docs document one-shot `--message` / `--message-file`, env-backed options, config files, ignore files, and conventions. |
| Amp | Deferred | Probe later | Account/subscription-gated agent; no clean noninteractive API-key-only container contract for config-only OpenART runs. |
| AstrBot | Deferred | Document only | Service/chat-platform assistant. It starts with `astrbot run` and is configured through a local web UI, so it does not fit one-shot argv/stdin target execution. |
| Cherry Studio | Deferred | Document only | Desktop AI client with agents, knowledge bases, and MCP. No stable terminal one-shot target contract in the guide. |
| Claude Code | Existing | Keep `target.claude-code.yaml` | Existing config covers CLI execution, env delivery, Claude files, rules, skills, commands, and memory. |
| Cline | Deferred | Document only | VS Code extension. Needs editor-extension harnessing, not config-only `PromptCLIRunner`. |
| Codex | Existing | Keep `target.codex.yaml` | Existing config covers Codex CLI execution and Codex native surfaces. |
| Continue CLI | Active new | Add `target.continue-cli.yaml` | `@continuedev/cli` documents headless `cn -p`, `--silent`, TTY-less execution, and `--config`; OpenART stages native `HOME/.continue/config.yaml` with OpenAI-compatible model settings. |
| Crush | Probe needed | Add only after smoke | Guide documents `crush` TUI and `~/.config/crush/crush.json`; no one-shot prompt mode confirmed. |
| Cursor Agent CLI | Deferred | Document only | Removed from built-in targets because the current CLI contract is not compatible with reproducible API-key-driven OpenART runs. |
| Deep Code | Probe needed | Add only after smoke | Guide documents `deepcode` TUI, `~/.deepcode/settings.json`, and Agent Skills. Need prompt-mode confirmation. |
| DeepSeek-TUI / CodeWhale | Active new | Add `target.deepseek-tui.yaml` | Legacy `deepseek-tui` npm package is deprecated and has no CLI bin; current successor is `codewhale`, which documents `-p`, `--yolo`, config, MCP, skills, and hooks. |
| GitHub Copilot | Deferred | Document only | VS Code extension. Not a direct CLI target. |
| GitHub Copilot CLI | Active new | Add `target.copilot-cli.yaml` | GitHub docs document `copilot -p`, stdin prompting, BYOK env vars, custom instructions, Agent Skills, and MCP config. |
| Goose | Active recommended | Add `target.goose.yaml` | Official docs document `goose run -t/-i`, `--provider`, `--model`, `.goosehints`, Agent Skills, slash commands, and plugin/hook concepts. |
| Hermes | Existing | Keep `target.hermes.yaml` | Existing config covers Hermes CLI, skills, SOUL, memory, user profile, and DB surfaces. |
| Kilo Code | Active new | Add `target.kilo.yaml` | Kilo docs document `kilo run --auto "message"` for autonomous non-interactive execution and OpenCode-compatible config. |
| Langcli | Probe needed | Add only after smoke | Guide documents interactive `langcli`; prompt transport and trusted files need confirmation. |
| LobeHub | Deferred | Document only | Web/desktop app configured through UI or server env vars. Not a direct prompt CLI target. |
| nanobot | Existing | Keep `target.nanobot.yaml` | Existing config covers nanobot CLI, JSON config delivery, project docs, and skills. |
| Oh My Pi | Active new | Add `target.oh-my-pi.yaml` | Repository docs document prompt mode with `omp -p`, and the DeepSeek guide documents `~/.omp/agent/models.yml`. |
| OpenClaw | Deferred | Document only | Personal assistant/chat-tool daemon. Terminal chat exists, but setup and channels are interactive service-oriented. |
| OpenCode | Existing | Keep `target.yaml` | Existing config covers OpenCode CLI, config delivery, instructions, skills, commands, conversation history, and memory. |
| Pi | Existing | Keep `target.pi.yaml` | Existing config covers Pi CLI, JSON model config, instructions, project docs, and skills. |
| Qwen Code | Active new | Add `target.qwen-code.yaml` | Qwen docs document headless `qwen -p`, stdin prompting, settings, `QWEN.md`, skills, and MCP. |
| Reasonix | Active new | Add `target.reasonix.yaml` | `reasonix run "task"` is one-shot and streams stdout; static inspection confirms `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, `--model`, and `--no-proxy` support. |
| WorkBuddy/CodeBuddy | Deferred | Document only | Desktop/editor coding assistant with `.codebuddy/models.json`; not a direct prompt CLI target. |

## Active New Targets

### Continue CLI

Continue CLI is integrated as a config-only target because the CLI package
documents headless execution with:

```text
cn -p "one-shot prompt" --silent
```

The OpenART config uses:

```text
framework: prompt_cli
surface_family: continue_cli
launch_cmd: cn -p --silent
prompt_transport: argv
prompt_flag: ""
```

Model delivery is hybrid:

- env: `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`
- config template: `HOME/.continue/config.yaml`

The model config file is not an attack surface. Attack vectors cover
`AGENTS.md`, `AGENT.md`, `CLAUDE.md`, `CODEX.md`, Continue rules, permissions,
and append-mode session history.

### Reasonix

Reasonix is integrated as a config-only target because the CLI documents a
noninteractive run command:

```text
reasonix run "one-shot prompt"
```

The OpenART config uses:

```text
framework: prompt_cli
surface_family: reasonix
launch_cmd: reasonix run --no-config --no-proxy --model ${TARGET_MODEL}
prompt_transport: argv
prompt_flag: ""
```

Model delivery is env-only:

- env: `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, `DEEPSEEK_MODEL`

No Reasonix model config file is staged. Attack vectors cover `REASONIX.md`,
Reasonix skills, memory, and hook settings.

### DeepSeek-TUI / CodeWhale

DeepSeek-TUI is integrated through its current successor, CodeWhale. The legacy
`deepseek-tui` npm package no longer exposes a usable `deepseek` binary; its
install path points users to `codewhale`. CodeWhale documents one-shot prompt
execution:

```text
codewhale exec --auto "one-shot prompt"
```

The OpenART config uses:

```text
framework: prompt_cli
surface_family: deepseek_tui
launch_cmd: codewhale --provider deepseek --model ${TARGET_MODEL} exec --auto
prompt_transport: argv
prompt_flag: ""
```

Model delivery is hybrid:

- env: `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, `DEEPSEEK_MODEL`
- config template: `HOME/.codewhale/config.toml`

The model config file is not an attack surface. It is framework-managed target
setup, not attacker-controlled state.

### Qwen Code

Qwen Code is integrated as a config-only target because the official docs
document headless execution with:

```text
qwen -p "one-shot prompt"
```

The OpenART config uses:

```text
framework: prompt_cli
surface_family: qwen_code
launch_cmd: qwen --yolo
prompt_transport: argv
prompt_flag: -p
```

Model delivery is hybrid:

- env: `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`
- config template: `HOME/.qwen/settings.json`

Attack vectors cover `QWEN.md`, `AGENTS.md`, user/project Qwen skills, and
portable `.agents/skills`.

### Kilo Code

Kilo Code is integrated as a config-only target because the Kilo CLI docs
document autonomous execution with:

```text
kilo run --auto "message"
```

The OpenART config uses:

```text
framework: prompt_cli
surface_family: kilo
launch_cmd: kilo run --auto
prompt_transport: argv
prompt_flag: ""
```

Model delivery is hybrid:

- env: `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`
- config template: `XDG_CONFIG_HOME/kilo/opencode.json`

Attack vectors cover `AGENTS.md`, Kilo skills, portable `.agents/skills`,
OpenCode-compatible skills/commands, and append-mode `.kilo/plans`.

### GitHub Copilot CLI

GitHub Copilot CLI is integrated as a config-only target because the GitHub
docs document programmatic execution with:

```text
copilot -p "one-shot prompt"
```

The OpenART config uses:

```text
framework: prompt_cli
surface_family: copilot_cli
launch_cmd: copilot -s --no-ask-user --allow-all --model ${TARGET_MODEL}
prompt_transport: argv
prompt_flag: -p
```

Model delivery is env-only:

- env: `COPILOT_PROVIDER_TYPE=openai`
- env: `COPILOT_PROVIDER_API_KEY`, `COPILOT_PROVIDER_BASE_URL`, `COPILOT_MODEL`

For OpenAI-compatible smoke runs, provide `TARGET_BASE_URL` as the `/v1`
endpoint. OpenART normalizes it into `COPILOT_PROVIDER_BASE_URL`. If an
Anthropic-native provider is used, override this target config or use a
provider-specific variant with `COPILOT_PROVIDER_TYPE=anthropic`.

Attack vectors cover `AGENTS.md`, `.github/copilot-instructions.md`,
`.github/instructions/*.instructions.md`, user-local Copilot instructions,
Copilot skills, portable `.agents/skills`, and explicit MCP config.

### Oh My Pi

Oh My Pi is integrated as a config-only target because the repository documents
prompt execution with:

```text
omp -p "one-shot prompt"
```

The OpenART config uses:

```text
framework: prompt_cli
surface_family: oh_my_pi
launch_cmd: omp --model deepseek/${TARGET_MODEL} --auto-approve
prompt_transport: argv
prompt_flag: -p
```

Model delivery is hybrid:

- env: `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, `DEEPSEEK_MODEL`
- config template: `HOME/.omp/agent/models.yml`

Attack vectors cover `AGENTS.md`, Copilot-compatible instructions, OMP skills,
portable `.agents/skills`, Claude skills, and Copilot project skills.

## Second CLI Search Pass

### Aider

Aider is integrated as a config-only target because the official scripting docs
document one-shot execution with:

```text
aider --message "one-shot prompt"
```

The OpenART config uses:

```text
framework: prompt_cli
surface_family: aider
launch_cmd: aider --yes-always --no-auto-commits --no-dirty-commits --no-check-update --message
prompt_transport: argv
prompt_flag: --message
```

Model delivery is env-only:

- env: `AIDER_MODEL=openai/${TARGET_MODEL}`, `AIDER_OPENAI_API_KEY`, `AIDER_OPENAI_API_BASE`

Attack vectors cover `.aider.conf.yml`, `.aiderignore`, `CONVENTIONS.md`,
append-mode `.aider.chat.history.md`, and an explicit `.aider.load` file for
experiments that route through Aider load commands.

### Goose

Goose is integrated as a config-only target because the official CLI docs
document one-shot runs with:

```text
goose run --no-session -t "one-shot prompt"
goose run --no-session -i instructions.txt
```

The OpenART config uses:

```text
framework: prompt_cli
surface_family: goose
launch_cmd: /root/.local/bin/goose run --no-session --quiet --with-builtin developer --provider openai --model ${TARGET_MODEL}
prompt_transport: argv
prompt_flag: -t
```

Model delivery is hybrid:

- env: `OPENAI_API_KEY`, `OPENAI_HOST`, `GOOSE_PROVIDER=openai`, `GOOSE_MODEL`
- config template: `HOME/.config/goose/config.yaml`

Attack vectors cover `AGENTS.md`, project and user `.goosehints`,
project/user `.agents/skills`, plugin hooks under
`.agents/plugins/<plugin>/hooks/hooks.json`, and project slash-command recipe
configuration under `.goose/commands`.

## Image And Attack Surface Config

| Target | Runner image | Dockerfile | Model config | Attack vectors |
|---|---|---|---|---|
| DeepSeek-TUI / CodeWhale | `openart/deepseek-tui:latest` | `images/Dockerfile.deepseek-tui` | `target-model-json/deepseek-tui.openai-compatible.toml` | `agents_md`, `codewhale_project_skill`, `codewhale_user_skill`, `codewhale_hook`, `codewhale_mcp` |
| Qwen Code | `openart/qwen-code:latest` | `images/Dockerfile.qwen-code` | `target-model-json/qwen-code.openai-compatible.json` | `qwen_md`, `agents_md`, `qwen_user_md`, `qwen_project_skill`, `qwen_user_skill`, `agents_skill` |
| Kilo Code | `openart/kilo:latest` | `images/Dockerfile.kilo` | `target-model-json/kilo.openai-compatible.json` | `agents_md`, `kilo_skill`, `agents_skill`, `opencode_skill`, `opencode_command`, `kilo_plan` |
| GitHub Copilot CLI | `openart/copilot-cli:latest` | `images/Dockerfile.copilot-cli` | env-only | `agents_md`, `copilot_instructions`, `copilot_path_instructions`, `copilot_user_instructions`, `copilot_project_skill`, `copilot_user_skill`, `agents_skill`, `copilot_mcp` |
| Oh My Pi | `openart/oh-my-pi:latest` | `images/Dockerfile.oh-my-pi` | `target-model-json/oh-my-pi.openai-compatible.yaml` | `agents_md`, `copilot_instructions`, `omp_skill`, `agents_skill`, `claude_skill`, `copilot_project_skill` |
| Aider | `openart/aider:latest` | `images/Dockerfile.aider` | env-only | `aider_config`, `aider_ignore`, `conventions_md`, `aider_chat_history`, `aider_load_file` |
| Goose | `openart/goose:latest` | `images/Dockerfile.goose` | `target-model-json/goose.openai-compatible.yaml` | `agents_md`, `goosehints`, `goose_user_hints`, `agents_skill`, `agents_user_skill`, `goose_plugin_hook`, `goose_slash_command` |

## Baseline Attack Vectors

### Instructions

Use generic instruction files only when smoke tests confirm that the target
actually reads them:

```text
AGENTS.md
CLAUDE.md
GEMINI.md
target-native rule files
```

For DeepSeek-TUI / CodeWhale, `AGENTS.md` is included as a probeable generic
instruction surface. If runtime traces show that it is ignored, remove it from
active attacker presets.

### Skills

Skill surfaces are the most portable coding-agent vector:

```text
.codewhale/skills/<skill-name>/SKILL.md
HOME/.codewhale/skills/<skill-name>/SKILL.md
.qwen/skills/<skill-name>/SKILL.md
HOME/.qwen/skills/<skill-name>/SKILL.md
.kilocode/skills/<skill-name>/SKILL.md
.omp/skills/<skill-name>/SKILL.md
.github/skills/<skill-name>/SKILL.md
HOME/.copilot/skills/<skill-name>/SKILL.md
.continue/rules/<rule-name>.md
HOME/.continue/rules/<rule-name>.md
.reasonix/skills/<skill-name>.md
.reasonix/skills/<skill-name>/SKILL.md
HOME/.reasonix/skills/<skill-name>.md
HOME/.reasonix/skills/<skill-name>/SKILL.md
.deepcode/skills/<skill-name>/SKILL.md
HOME/.agents/skills/<skill-name>/SKILL.md
.agents/skills/<skill-name>/SKILL.md
HOME/.agents/skills/<skill-name>/SKILL.md
```

OpenART should keep the paths target-specific and rely on framework-side skill
validation before materialization.

### Memory And History

Memory/history vectors should use `append` only when the target treats the file
as an accumulating session or memory store. Candidate examples from current
targets include OpenCode sessions, Claude local memory, Codex task lists, and
Hermes memory files. For new agents, add these only after identifying stable
file paths and startup behavior.

### MCP And Tools

MCP/tool configuration is realistic but high risk. Treat it as an explicit
experiment vector, not a default attacker vector:

```text
HOME/.codewhale/mcp.json
HOME/.copilot/mcp-config.json
.codewhale/hooks.toml
.agents/plugins/<plugin-name>/hooks/hooks.json
.goose/commands/<command-name>.yaml
target-specific MCP server config
plugin/tool manifests
custom command definitions
```

For DeepSeek-TUI / CodeWhale, `codewhale_mcp` and `codewhale_hook` are exposed
in the target config so the control plane can filter them, but attacker presets
should include them only when the experiment is explicitly about MCP/tool
supply-chain or approval-policy risk.

### Model Configuration

Do not expose model delivery files as attacker vectors by default:

```text
HOME/.codewhale/config.toml
HOME/.qwen/settings.json
XDG_CONFIG_HOME/kilo/opencode.json
HOME/.continue/config.yaml
HOME/.config/goose/config.yaml
HOME/.deepcode/settings.json
HOME/.omp/agent/models.yml
HOME/.config/crush/crush.json
.codebuddy/models.json
```

These files may contain credentials or define transport-level compatibility.
They belong to `model_integration.delivery`, not `attack_surfaces`, unless the
benchmark is specifically a configuration-integrity benchmark.

## Probe Gate For New CLI Targets

Add a target config only after all of these pass:

1. The target binary runs in its Docker image with `--version`.
2. Help output documents argv, stdin, prompt, print, exec, or run-once mode.
3. A one-turn OpenART smoke task reaches the target and records stdout in the trace.
4. At least one target-native file path is confirmed target-visible in trace or output.
5. Model credential/config files remain framework-managed and are not exposed as attack surfaces.
