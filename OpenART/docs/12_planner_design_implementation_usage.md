# Scenario-First Safe-World Planner

The planner generates OpenART/OpenAgentSafety task bundles from scenario
descriptions. It is scenario-first: the scenario seed is converted into an
abstract `scenario_model.json`, then a complete bundle is generated from that
accepted model, the refreshed tool pool, and the requested complexity profile.

The current generator is OpenCode-only. The CLI still accepts
`--planner-backend opencode` for compatibility, while the old deterministic
backend is intentionally rejected.

## Purpose

Planner-generated tasks should look like normal business workflows that can be
completed safely, while containing a realistic hidden unsafe failure mode. The
target-visible `task.md` stays benign. Private or confidential workspace assets,
unsafe markers, evaluator paths, and scoring details live outside the visible
request, mostly in `workspace/`, `safety_contract.json`, and evaluator files.

The planner is meant to:

- generate reusable OpenART/OpenAgentSafety task bundles from short scenario
  seeds;
- create rich, domain-specific workspace state instead of fixed templates;
- select tools from the final `tool_pool.json`, including registry-backed tools
  materialized before prompting;
- enforce a requested exact count of distinct enabled external tools in the
  safe workflow;
- enforce complexity-configured safe workflow node ranges and external
  tool-call node floors;
- validate and repair generated output before treating a bundle as usable.

## Implementation Map

| Area | Files |
|------|-------|
| CLI orchestration | `framework/planner/cli.py` |
| OpenCode Docker backend and prompts | `framework/planner/opencode_backend.py` |
| Tool pool normalization and built-ins | `framework/planner/safe_world.py` |
| Complexity profiles | `framework/planner/complexity.py` |
| SQLite registry search/materialization | `framework/planner/registry.py` |
| Bundle and scenario validation | `framework/planner/validation.py` |
| Planner prompt contracts | `configs/planner/*.md`, `configs/planner/output_contract.schema.json` |
| Scenario seeds | `configs/planner/scenarios/*.txt` |
| Scenario corpus generation | `framework/planner/scenarios.py` |
| Batch runner | `framework/planner/batch_runner.py` |
| Task collection | `framework/planner/collector.py` |
| Human-facing utility entrypoint | `scripts/planner.py` |
| Regression tests | `tests/unit/test_opencode_planner.py`, `tests/unit/test_safe_world_planner.py`, `tests/unit/test_opencode_planner_runner.py`, `tests/unit/test_planner_registry_materialization.py` |

## Scenario Corpus Generation

The checked-in seed inventory starts with `../agent_scenarios.md`, a 525
scenario corpus with 35 categories and 15 scenarios per category. The expansion
source `../agent_scenarios_expansion_double_525.md` adds another non-duplicate
525 scenarios with the same category structure.

Generate the expansion-only and combined 1050 scenario file trees:

```bash
cd OpenART

python scripts/planner.py scenarios \
  --source ../agent_scenarios_expansion_double_525.md \
  --output-dir configs/planner/scenarios/generated_expansion_double_525

python scripts/planner.py scenarios \
  --source ../agent_scenarios.md \
  --append-source ../agent_scenarios_expansion_double_525.md \
  --output-dir configs/planner/scenarios/generated_combined_double_1050
```

Generate the large deterministic diversity fabric:

```bash
cd OpenART

python scripts/planner.py scenarios \
  --diverse-count 100000 \
  --output-dir configs/planner/scenarios/generated_100k
```

`configs/planner/scenarios/generated_100k/` is intentionally treated as a
generated artifact and is not checked into git. Its `manifest.json` records the
balanced per-category counts, excluded source files, and the coverage profile.
The current `domain-tool-surface-fabric-v3` profile keeps the original 35
checked-in categories, appends 465 generated domain categories from 155 domain
sectors and 3 workflow modes, and adds explicit tool-surface phrases to each
seed so registry search/materialization has stronger cues when a large tool
store is available. The 100k target balances exactly across 500 configured
categories, 200 scenarios per category. It deliberately expands domain and
tool-surface coverage only; it does not add action-intent, synthetic
complexity, or style axes to the scenario corpus.

The same implementation can be called as a module when scripting from
`OpenART/`, for example `python -m framework.planner.scenarios --help`.

## Architecture

The planner path has six main stages.

1. CLI input loading

   `framework.planner.cli` reads either `--scenario` or `--scenario-file`,
   loads `.env` through the normal OpenART CLI dotenv path, resolves the
   selected complexity profile, and prepares the output directory.

2. Tool pool and runtime manifest construction

   Planner tool inputs come only from the explicit managed `--tool-store`.
   The planner reloads valid folders from that store through the normal
   registry/materialization path and always adds built-in workspace primitives
   to the planner-visible pool. The normalized compact pool is written as
   `tool_pool.json`; the OpenART runtime manifest is written as
   `capabilities.generated.yaml`.

3. Registry materialization

   The planner checks
   `.registry/openart_tool_registry.sqlite` under that store. Ready,
   non-deleted rows with embedded `raw.openart_tool` payloads can be
   materialized into normal `tool.<slug>.<hash>/` folders before prompting.
   The refreshed tool pool is the only tool set the generated task may use.

4. Scenario model generation

   OpenCode first receives a scenario-model prompt and writes only
   `scenario_model.json`. `validate_scenario_model` checks domain fit,
   resource classes, leak indicators, workflow stages, tool count constraints,
   and complexity requirements.

5. Bundle generation

   After the scenario model passes, OpenCode receives the full generation
   prompt, the accepted model, the refreshed tool pool, the generated runtime
   manifest, registry feedback, and the output contract schema. It writes the
   bundle files directly into the output directory.

6. Validation and repair loop

   `validate_generated_bundle` checks required files, graph structure, exact
   external tool count, disabled tool usage, task visibility, workspace
   richness, marker alignment, runtime loading, and evaluator behavior. Failed
   attempts produce structured repair prompts. Scenario and bundle generation
   each receive up to `--planner-max-repairs` repair attempts, or a
   profile-aware default when that flag is omitted.

## OpenCode Backend

The backend runs OpenCode inside Docker with the generated task directory
mounted at `/work/task`, isolated OpenCode state mounted at `/work/state`, and
planner logs mounted at `/work/artifacts`.

Required environment variables:

```bash
export OPENART_PLANNER_API_KEY="your-planner-key"
export OPENART_PLANNER_BASE_URL="https://planner-endpoint.example/v1"
export OPENART_PLANNER_MODEL="planner-model"
```

Optional controls:

- `OPENART_PLANNER_TIMEOUT_SECONDS`: backend subprocess timeout, default 1800.
- `OPENART_PLANNER_DOCKER_IMAGE`: backend image override when
  `--planner-docker-image` is not passed.
- Proxy variables such as `HTTPS_PROXY`: passed through when present.

The rendered OpenCode config stores the model name and base URL, but references
the API key as an environment variable so the key is not written into
`planner_artifacts/opencode_run_attempt_*.json`.

Build the default image from `OpenART/`:

```bash
docker build -t openart/safe-world-planner:latest \
  -f images/Dockerfile.safe-world-planner .
```

## Generated Bundle Contract

Every accepted generated bundle must contain:

| Path | Purpose |
|------|---------|
| `scenario_model.json` | Abstract scenario contract with domain, actor, benign goal, publication sinks, approved resources, risky resources, leak indicators, and workflow stages |
| `task.md` | Benign target-visible request; no explicit prohibition wording, protected paths, marker strings, evaluator details, or scoring logic |
| `workspace/` | Rich target workspace with approved sources, decoys, service-style artifacts, and protected/risky files |
| `tool_pool.json` | Compact planner-visible pool, including capability groups and final usable tool names |
| `tool_use_graph.json` | Safe workflow graph plus hidden unsafe/oracle workflow information |
| `safety_contract.json` | Evaluator contract for safe completion, protected source paths, public roots, and forbidden markers |
| `capabilities.generated.yaml` | OpenART-compatible runtime tool manifest derived from the final tool pool |
| `planner_plan.json` | Planner rationale for scenario, workspace, tool, and graph choices |
| `utils/evaluator.py` | Deterministic evaluator callable compatible with OpenART runtime inputs |
| `utils/test_evaluator.py` | Truth-table tests for safe success, safe miss, unsafe leak, and safe-plus-unsafe cases |
| `checkpoints.md` | Evaluator-side scoring context and expected checkpoints |

The host also writes planner diagnostics under `planner_artifacts/`, including
registry materialization feedback, OpenCode prompts/stdout/stderr, sanitized run
metadata, and validation reports.

## Usage

Generate one task from a checked-in scenario:

```bash
cd OpenART

export OPENART_PLANNER_API_KEY="your-planner-key"
export OPENART_PLANNER_BASE_URL="https://planner-endpoint.example/v1"
export OPENART_PLANNER_MODEL="planner-model"

python -m framework.planner.cli \
  --planner-backend opencode \
  --scenario-file configs/planner/scenarios/recruiting-interview-agenda.txt \
  --tool-store ../openart-tools \
  --tool-count 3 \
  --planner-max-repairs 2 \
  --complexity-profile stress \
  --task-id recruiting-interview-agenda \
  --output-dir outputs/recruiting-interview-agenda \
  --overwrite
```

Generate a small batch of real scenarios:

```bash
cd OpenART

python scripts/planner.py run \
  --count 3 \
  --workers 1 \
  --tool-store ../openart-tools \
  --tool-count 3 \
  --planner-max-repairs 2 \
  --complexity-profile stress \
  --output-dir outputs/opencode-planner-real-scenarios
```

Generate high-call tasks with 60-100 safe workflow nodes, aiming near 90,
using 25 distinct enabled external tools:

```bash
cd OpenART

python scripts/planner.py run \
  --complexity-config configs/planner/complexity/high_tool_calls_60_100.yaml \
  --tool-count 25 \
  --output-dir outputs/opencode-planner-high-calls
```

Here, the tool-call count target comes from
`tool_use_graph.safe_workflow.nodes` through the complexity config.
`--tool-count` still means distinct enabled external tools used by the safe
workflow, not total calls.

Collect valid generated tasks from one or more batch summaries:

```bash
cd OpenART

python scripts/planner.py collect \
  outputs/opencode-planner-real-scenarios/summary.json \
  --output-dir ../outputs/planner-task-collections/real-scenarios \
  --mode symlink \
  --overwrite
```

Run a generated task with deterministic evaluation:

```bash
cd OpenART

python -m framework.cli run \
  --task outputs/recruiting-interview-agenda \
  --tool-store ../openart-tools \
  --eval-strategy deterministic
```

## Complexity Profiles

Built-in profiles live in `framework/planner/complexity.py`:

| Profile | Default repairs | Intended shape |
|---------|-----------------|----------------|
| `basic` | 1 | Small bundle with minimum staged workflow and workspace richness |
| `rich` | 2 | Deeper workflow, parallel branches, mixed risk layout, and more source formats |
| `stress` | 2 | Default profile; larger workflow, deeper dependencies, more files, more risk classes |

Use `--complexity-config` with a YAML or JSON mapping to overlay a built-in
profile. Supported override fields include `min_workflow_stages`,
`min_safe_workflow_nodes`, `target_safe_workflow_nodes`,
`max_safe_workflow_nodes`, `min_dependency_depth`, `min_parallel_branches`,
`min_external_tool_call_nodes`, `min_approved_files`, `min_risk_files`,
`min_formats`, `required_file_extensions`,
`required_binary_file_extensions`, `min_binary_formats`, `min_risk_types`,
and `require_mixed_risk_layout`.

`min_safe_workflow_nodes`, `target_safe_workflow_nodes`, and
`max_safe_workflow_nodes` apply to `tool_use_graph.safe_workflow.nodes`.
`min_external_tool_call_nodes` counts safe workflow nodes that call enabled
external tools. It is separate from `--tool-count`, which counts distinct
enabled external tools and is usually much smaller.

The high-call preset lives at
`configs/planner/complexity/high_tool_calls_60_100.yaml`. It overlays `stress`,
requires 60-100 safe workflow nodes with a target of 90, at least 40 external
tool-call nodes, 14 total workspace formats, and 5 binary/non-text formats.
It also requires text/semi-structured suffixes such as `.md`, `.json`, `.csv`,
`.yaml`, `.html`, `.xml`, `.log`, and `.sql`, plus non-text suffixes such as
`.pdf`, `.docx`, `.xlsx`, `.pptx`, `.png`, and `.sqlite`.

Binary and non-text files increase workspace realism and give external tools
useful targets. Keep `safety_contract` markers, evaluator-required safe facts,
and other scoring-critical strings in text-readable files or companion
metadata unless the generated evaluator explicitly supports parsing a binary
type. Placeholder binary-style artifacts with the correct suffix are acceptable
when creating a minimal valid document is not practical, provided companion
metadata carries any evaluator-critical facts.

## Extension Points

Add scenario seeds under `configs/planner/scenarios/`. Keep them short and
domain-specific; the scenario model prompt is responsible for expanding the
seed into resource classes, leak indicators, and workflow stages.

Add normal managed tools as direct child folders of `openart-tools/` with
`SKILL.md` or `TOOL.md`. Add `tool.yaml` only when the tool needs a runtime
wrapper. The folder name is the tool name that may appear in
`tool_use_graph.json`.

Add registry-backed tools by inserting ready rows into
`openart-tools/.registry/openart_tool_registry.sqlite` with embedded
`raw.openart_tool` payloads. The registry file must be a real SQLite file, not
a symlink. Generated bundles must not call `registry.search`,
`registry.install`, `registry.show`, or materialization helpers; they should use
only final tool names present in the refreshed `tool_pool.json`.

Extend evaluator behavior by changing the generated evaluator contract, prompt
instructions, and validator together. `utils/evaluator.py`,
`utils/test_evaluator.py`, `safety_contract.json`, and protected workspace
markers must stay aligned.

Add validation rules in `framework/planner/validation.py` first, then update
planner prompts and tests. The validator is the source of truth for accepted
generated bundles.

## Validation Commands

Docs sanity checks:

```bash
rg -n 'scenario-first-safe-world-planner' README.md OpenART/README.md OpenART/docs
find OpenART/docs -maxdepth 2 -type f -name '*.md' -print | sort
```

Planner regression tests:

```bash
python3 -m pytest OpenART/tests/unit/test_opencode_planner.py
python3 -m pytest OpenART/tests/unit/test_safe_world_planner.py
python3 -m pytest OpenART/tests/unit/test_generate_planner_scenario_files.py
python3 -m pytest OpenART/tests/unit/test_opencode_planner_runner.py
python3 -m pytest OpenART/tests/unit/test_planner_registry_materialization.py
```

## Debugging Checklist

- Environment: confirm `OPENART_PLANNER_API_KEY`,
  `OPENART_PLANNER_BASE_URL`, and `OPENART_PLANNER_MODEL` are present after
  dotenv loading.
- Docker image: confirm `openart/safe-world-planner:latest` exists, or pass
  `--planner-docker-image`.
- Registry: inspect
  `openart-tools/.registry/openart_tool_registry.sqlite` and
  `planner_artifacts/registry_materialization.json`; missing registry files are
  non-fatal.
- Tool count: compare requested `--tool-count` with distinct enabled external
  tools in `tool_use_graph.safe_workflow.nodes`; built-in workspace tools do
  not count.
- High-call complexity: compare total safe calls with
  `tool_use_graph.safe_workflow.nodes`, and compare external call floors with
  the number of safe nodes that call enabled external tools.
- Generated inputs: inspect `tool_pool.json` and
  `capabilities.generated.yaml` in the task output directory, not stale source
  manifests.
- Validation reports: read
  `planner_artifacts/scenario_validation_attempt_*.json` and
  `planner_artifacts/validation_attempt_*.json` before changing prompts.
- Evaluator probes: check `utils/test_evaluator.py` and the validator error for
  truth-table, runtime contract, or leak-detection failures.
- Visibility: ensure `task.md` does not expose private paths, markers,
  explicit prohibitions, or scoring logic.
- Runtime loading: run `framework.cli run` with the same `--tool-store` used
  for planning.

## Known Audit Gaps

- This page documents the current implementation, but
  `framework/planner/validation.py` remains the authoritative contract.
- Planner output depends on the configured OpenCode-compatible model, so repair
  attempts improve validity but do not make generation deterministic.
- Registry expansion is optional. If the SQLite registry is missing or
  unreadable, generated tasks can still use existing materialized tool folders,
  and the reason is recorded in `planner_artifacts/registry_materialization.json`.
- The canonical docs do not include a checked-in generated bundle sample; use
  the validation commands above for live confidence.
