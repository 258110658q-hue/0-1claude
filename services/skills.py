"""技能系统 — s07"""
import yaml
from config import SKILLS_DIR

def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """解析 SKILL.md 的 YAML 头部元数据。返回 (元数据字典, 正文)。"""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    try:
        meta = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        meta = {}
    return meta, parts[2].strip()
SKILL_REGISTRY: dict[str, dict] = {}
def _scan_skills():
    """启动时扫描 skills/ 目录，将名称/简介/完整内容填入注册表。"""
    if not SKILLS_DIR.exists():
        return
    for d in sorted(SKILLS_DIR.iterdir()):
        if not d.is_dir():
            continue
        manifest = d / "SKILL.md"
        if manifest.exists():
            raw = manifest.read_text(encoding="utf-8")
            meta, body = _parse_frontmatter(raw)
            name = meta.get("name", d.name)
            desc = meta.get("description", raw.split("\n")[0].lstrip("#").strip())
            SKILL_REGISTRY[name] = {"name": name, "description": desc, "content": raw}

_scan_skills()  # 启动时执行一次
def list_skills() -> str:
    """列出所有可用技能（名称 + 一句话简介）。"""
    if not SKILL_REGISTRY:
        return "（未找到技能）"
    return "\n".join(f"- **{s['name']}**：{s['description']}" for s in SKILL_REGISTRY.values())
def load_skill(name: str) -> str:
    """从注册表查找技能并返回完整内容。不走文件路径，防路径遍历。"""
    skill = SKILL_REGISTRY.get(name)
    if not skill:
        return f"未找到技能: {name}"
    return skill["content"]
