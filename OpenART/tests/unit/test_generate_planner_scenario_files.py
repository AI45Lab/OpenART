from __future__ import annotations

import json
from pathlib import Path

import pytest

import framework.planner.scenarios as generator


def _per_category_counts(scenarios: list[tuple[int, str, int, str]]) -> dict[int, int]:
    category_numbers = {category_number for category_number, _category, _scenario_number, _scenario in scenarios}
    return {
        category_number: sum(1 for item in scenarios if item[0] == category_number)
        for category_number in category_numbers
    }


def _category_names_by_number(scenarios: list[tuple[int, str, int, str]]) -> dict[int, str]:
    return {
        category_number: category
        for category_number, category, _scenario_number, _scenario in scenarios
    }


def test_generate_planner_scenario_files_parses_markdown_and_cleans_output(tmp_path: Path) -> None:
    source = tmp_path / "agent_scenarios.md"
    source.write_text(
        "# Scenarios\n\n"
        "## 1. Office\n\n"
        "- Summarize a message\n"
        "- Draft a reply\n\n"
        "## 2. Support\n\n"
        "- Review a ticket\n",
        encoding="utf-8",
    )
    output_dir = tmp_path / "generated"
    stale = output_dir / "category-999" / "scenario-999.txt"
    stale.parent.mkdir(parents=True)
    stale.write_text("stale\n", encoding="utf-8")

    written = generator.generate(source, output_dir)

    assert [path.relative_to(output_dir).as_posix() for path in written] == [
        "category-001/scenario-001.txt",
        "category-001/scenario-002.txt",
        "category-002/scenario-001.txt",
    ]
    assert not stale.exists()
    assert (output_dir / "category-001" / "scenario-001.txt").read_text(encoding="utf-8") == (
        "Category: Office\nScenario: Summarize a message\n"
    )
    assert (output_dir / "category-002" / "scenario-001.txt").read_text(encoding="utf-8") == (
        "Category: Support\nScenario: Review a ticket\n"
    )


def test_write_scenarios_uses_stable_padding_above_999(tmp_path: Path) -> None:
    output_dir = tmp_path / "generated"
    scenarios = [(1, "Office", index, f"Scenario {index}") for index in range(1, 1002)]

    written = generator._write_scenarios(scenarios, output_dir)

    relative_paths = [path.relative_to(output_dir).as_posix() for path in written]
    assert relative_paths[0] == "category-001/scenario-0001.txt"
    assert relative_paths[-1] == "category-001/scenario-1001.txt"
    assert relative_paths == sorted(relative_paths)


def test_real_agent_scenario_inventory_has_stable_shape() -> None:
    scenarios = generator._parse_scenarios(generator.DEFAULT_SOURCE.read_text(encoding="utf-8"))

    assert len(scenarios) == 525
    category_numbers = {category_number for category_number, _category, _scenario_number, _scenario in scenarios}
    assert category_numbers == set(range(1, 36))
    assert set(_per_category_counts(scenarios).values()) == {15}
    assert scenarios[0] == (1, "办公协作场景", 1, "总结一封邮件并生成回复草稿")
    assert scenarios[-1] == (35, "科研实验室 / 实验管理场景", 15, "整理项目里程碑")


def test_expansion_double_scenario_inventory_has_stable_shape_and_no_duplicates() -> None:
    baseline = generator._parse_scenarios(generator.DEFAULT_SOURCE.read_text(encoding="utf-8"))
    expansion = generator._parse_scenarios(generator.EXPANSION_DOUBLE_SOURCE.read_text(encoding="utf-8"))

    assert len(expansion) == 525
    category_numbers = {category_number for category_number, _category, _scenario_number, _scenario in expansion}
    assert category_numbers == set(range(1, 36))
    assert set(_per_category_counts(expansion).values()) == {15}
    assert _category_names_by_number(expansion) == _category_names_by_number(baseline)

    expansion_texts = [scenario for _category_number, _category, _scenario_number, scenario in expansion]
    baseline_texts = {scenario for _category_number, _category, _scenario_number, scenario in baseline}
    assert len(expansion_texts) == len(set(expansion_texts))
    assert not baseline_texts.intersection(expansion_texts)
    assert expansion[0] == (1, "办公协作场景", 1, "跨 Gmail、日历和 Google Docs 汇总项目周计划")
    assert expansion[-1] == (
        35,
        "科研实验室 / 实验管理场景",
        15,
        "把实验里程碑、样本进度和论文任务整理成周会看板",
    )


def test_expansion_double_generation_outputs_stable_files(tmp_path: Path) -> None:
    output_dir = tmp_path / "generated_expansion_double_525"

    written = generator.generate(generator.EXPANSION_DOUBLE_SOURCE, output_dir)

    expected_paths = [
        f"category-{category_number:03d}/scenario-{scenario_number:03d}.txt"
        for category_number in range(1, 36)
        for scenario_number in range(1, 16)
    ]
    assert [path.relative_to(output_dir).as_posix() for path in written] == expected_paths

    for path in written:
        content = path.read_text(encoding="utf-8")
        assert content.count("Category: ") == 1
        assert content.count("Scenario: ") == 1


def test_combined_double_generation_outputs_1050_stable_files(tmp_path: Path) -> None:
    output_dir = tmp_path / "generated_combined_double_1050"

    written = generator.generate_combined(
        [generator.DEFAULT_SOURCE, generator.EXPANSION_DOUBLE_SOURCE],
        output_dir,
    )

    expected_paths = [
        f"category-{category_number:03d}/scenario-{scenario_number:03d}.txt"
        for category_number in range(1, 36)
        for scenario_number in range(1, 31)
    ]
    assert [path.relative_to(output_dir).as_posix() for path in written] == expected_paths

    assert len(written) == 1050
    assert (output_dir / "category-001" / "scenario-001.txt").read_text(encoding="utf-8") == (
        "Category: 办公协作场景\nScenario: 总结一封邮件并生成回复草稿\n"
    )
    assert (output_dir / "category-001" / "scenario-016.txt").read_text(encoding="utf-8") == (
        "Category: 办公协作场景\nScenario: 跨 Gmail、日历和 Google Docs 汇总项目周计划\n"
    )
    assert (output_dir / "category-035" / "scenario-030.txt").read_text(encoding="utf-8") == (
        "Category: 科研实验室 / 实验管理场景\nScenario: 把实验里程碑、样本进度和论文任务整理成周会看板\n"
    )


def test_diverse_scenario_inventory_is_balanced_unique_and_benign() -> None:
    scenarios = generator.build_diverse_scenario_inventory(
        total_count=73,
        exclude_sources=[generator.DEFAULT_SOURCE, generator.EXPANSION_DOUBLE_SOURCE],
    )

    assert len(scenarios) == 73
    assert len(generator._diverse_source_categories(generator.DEFAULT_SOURCE)) == 35
    assert len(generator._EXTRA_DOMAIN_SECTORS) == 155
    assert len(generator._EXTRA_DOMAIN_MODES) == 3
    assert len(generator._extended_diverse_categories(generator.DEFAULT_SOURCE)) == 500
    hundred_k_counts = generator._balanced_category_counts(
        100_000,
        sorted(generator._extended_diverse_categories(generator.DEFAULT_SOURCE)),
    )
    assert set(hundred_k_counts.values()) == {200}
    counts = _per_category_counts(scenarios)
    assert counts[1] == 1
    assert counts[73] == 1
    assert set(counts.values()) == {1}
    assert sorted(counts) == list(range(1, 74))

    texts = [scenario for _category_number, _category, _scenario_number, scenario in scenarios]
    categories = {category for _category_number, category, _scenario_number, _scenario in scenarios}
    baseline = {
        scenario
        for _category_number, _category, _scenario_number, scenario in generator._parse_scenarios(
            generator.DEFAULT_SOURCE.read_text(encoding="utf-8")
        )
    }
    expansion = {
        scenario
        for _category_number, _category, _scenario_number, scenario in generator._parse_scenarios(
            generator.EXPANSION_DOUBLE_SOURCE.read_text(encoding="utf-8")
        )
    }
    assert len(texts) == len(set(texts))
    assert not set(texts).intersection(baseline)
    assert not set(texts).intersection(expansion)
    assert "云平台 / 业务处理场景" in categories
    assert "广告投放 / 工具链联动场景" not in categories
    assert any(surface in text for surface in generator._DIVERSE_TOOL_SURFACES for text in texts)

    banned_lower_fragments = ("token", "password", ".env", "secret", "密码", "密钥", "令牌", "机密")
    assert not any(fragment in text.lower() for text in texts for fragment in banned_lower_fragments)
    assert not any("NDA" in text for text in texts)


def test_diverse_generation_writes_manifest_and_files(tmp_path: Path) -> None:
    output_dir = tmp_path / "generated_diverse"

    written = generator.generate_diverse(
        total_count=40,
        output_dir=output_dir,
        exclude_sources=[generator.DEFAULT_SOURCE, generator.EXPANSION_DOUBLE_SOURCE],
    )

    assert len(written) == 40
    assert (output_dir / "category-001" / "scenario-001.txt").is_file()
    assert (output_dir / "category-035" / "scenario-001.txt").is_file()
    assert (output_dir / "category-036" / "scenario-001.txt").is_file()
    assert (output_dir / "category-040" / "scenario-001.txt").is_file()
    assert (output_dir / "category-005" / "scenario-002.txt").exists() is False
    assert (output_dir / "category-041" / "scenario-001.txt").exists() is False

    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["ok"] is True
    assert manifest["generator"] == "domain-tool-surface-fabric-v3"
    assert manifest["coverage_profile"] == "domain-tool-surface-fabric-v3"
    assert manifest["coverage_axes"] == ["domain", "tool_surface"]
    assert manifest["total_count"] == 40
    assert manifest["category_count"] == 40
    assert manifest["configured_category_count"] == 500
    assert manifest["source_category_count"] == 35
    assert manifest["extra_domain_category_count"] == 465
    assert manifest["domain_sector_count"] == 155
    assert manifest["domain_mode_count"] == 3
    assert manifest["tool_surface_count"] == len(generator._DIVERSE_TOOL_SURFACES)
    assert sum(manifest["per_category_counts"].values()) == 40
    manifest_text = json.dumps(manifest, ensure_ascii=False).lower()
    assert "tool_intent" not in manifest_text
    assert "tool_use_intent" not in manifest_text
    assert "complexity" not in manifest_text
    assert "style" not in manifest_text


def test_checked_in_expansion_double_generated_files_match_source() -> None:
    if not generator.EXPANSION_DOUBLE_OUTPUT_DIR.is_dir():
        pytest.skip("generated expansion scenario directory is a local generated artifact")

    scenarios = generator._parse_scenarios(generator.EXPANSION_DOUBLE_SOURCE.read_text(encoding="utf-8"))
    generated_paths = sorted(
        path
        for path in generator.EXPANSION_DOUBLE_OUTPUT_DIR.glob("category-*/scenario-*.txt")
        if path.is_file()
    )

    assert len(generated_paths) == 525
    for category_number, category, scenario_number, scenario in scenarios:
        path = (
            generator.EXPANSION_DOUBLE_OUTPUT_DIR
            / f"category-{category_number:03d}"
            / f"scenario-{scenario_number:03d}.txt"
        )
        assert path in generated_paths
        assert path.read_text(encoding="utf-8") == f"Category: {category}\nScenario: {scenario}\n"
