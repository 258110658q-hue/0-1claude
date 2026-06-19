"""services/skills.py 测试 — 技能扫描/加载"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestParseFrontmatter:
    def test_valid_yaml(self):
        from services.skills import _parse_frontmatter
        text = "---\nname: test-skill\ndescription: A test skill\n---\n\n# Content"
        meta, body = _parse_frontmatter(text)
        assert meta["name"] == "test-skill"
        assert "# Content" in body

    def test_no_frontmatter(self):
        from services.skills import _parse_frontmatter
        meta, body = _parse_frontmatter("# Just content")
        assert meta == {}
        assert "Just content" in body

    def test_invalid_yaml_returns_empty(self):
        from services.skills import _parse_frontmatter
        text = "---\n:bad yaml:\n---\ncontent"
        meta, body = _parse_frontmatter(text)
        assert isinstance(meta, dict)


class TestSkillRegistry:
    def test_list_empty(self):
        from services.skills import list_skills, SKILL_REGISTRY
        SKILL_REGISTRY.clear()
        result = list_skills()
        assert "未找到" in result or "(no" in result.lower()

    def test_load_nonexistent(self):
        from services.skills import load_skill
        result = load_skill("nonexistent_skill")
        assert "未找到" in result or "not found" in result.lower()
