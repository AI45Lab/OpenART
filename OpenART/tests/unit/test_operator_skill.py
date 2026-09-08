from __future__ import annotations

from pathlib import Path
import re

import yaml


OPENART_ROOT = Path(__file__).resolve().parents[2]
SKILLS_ROOT = OPENART_ROOT / "skills"
FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", re.DOTALL)


def test_operator_skill_is_one_unified_entrypoint() -> None:
    skill_dirs = sorted(
        path.name
        for path in SKILLS_ROOT.iterdir()
        if path.is_dir() and not path.name.startswith(".")
    )
    assert skill_dirs == ["openart"]


def test_unified_operator_skill_has_valid_frontmatter_and_links() -> None:
    skill_path = SKILLS_ROOT / "openart" / "SKILL.md"
    text = skill_path.read_text(encoding="utf-8")
    match = FRONTMATTER.match(text)

    assert match is not None
    frontmatter = yaml.safe_load(match.group(1))
    body = match.group(2)
    assert frontmatter["name"] == "openart"
    assert frontmatter["description"]
    assert frontmatter["metadata"]["scope"] == "operator"
    assert set(frontmatter["metadata"]["audiences"]) == {"agent", "human"}
    assert "Use this skill when" in body

    markdown_links = re.findall(r"\]\(([^)]+)\)", body)
    for link in markdown_links:
        if link.startswith(("http://", "https://", "#")):
            continue
        target = (skill_path.parent / link).resolve()
        assert target.is_file(), f"broken operator skill link: {link}"
