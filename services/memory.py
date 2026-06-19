"""记忆系统 — s09"""
import json, re, time
from config import safe_print,  MEMORY_DIR, MEMORY_INDEX, client, PRIMARY_MODEL
from core.utils import extract_text

MEMORY_TYPES = ["user", "feedback", "project", "reference"]
CONSOLIDATE_THRESHOLD = 10   # 记忆文件数达到此值触发整理
def _parse_memory_frontmatter(text: str) -> tuple[dict, str]:
    """解析记忆文件的 YAML frontmatter（不用 yaml 库，避免依赖）。"""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    meta = {}
    for line in parts[1].strip().splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip('"').strip("'")
    return meta, parts[2].strip()
def write_memory_file(name: str, mem_type: str, description: str, body: str):
    """写单个记忆文件（YAML frontmatter + markdown 正文），写完后重建索引。"""
    MEMORY_DIR.mkdir(exist_ok=True)
    slug = name.lower().replace(" ", "-").replace("/", "-")
    filepath = MEMORY_DIR / f"{slug}.md"
    filepath.write_text(
        f"---\nname: {name}\ndescription: {description}\ntype: {mem_type}\n---\n\n{body}\n",
        encoding="utf-8"
    )
    _rebuild_index()
    return filepath
def _rebuild_index():
    """扫描 .memory/ 下所有 .md 文件，重建 MEMORY.md 索引。"""
    MEMORY_DIR.mkdir(exist_ok=True)
    lines = []
    for f in sorted(MEMORY_DIR.glob("*.md")):
        if f.name == "MEMORY.md":
            continue
        raw = f.read_text(encoding="utf-8")
        meta, body = _parse_memory_frontmatter(raw)
        name = meta.get("name", f.stem)
        desc = meta.get("description", body.split("\n")[0][:80])
        lines.append(f"- [{name}]({f.name}) — {desc}")
    MEMORY_INDEX.write_text("\n".join(lines) + "\n" if lines else "", encoding="utf-8")
def read_memory_index() -> str:
    """读 MEMORY.md 索引（注入 SYSTEM，每轮都带）。"""
    if not MEMORY_INDEX.exists():
        return ""
    text = MEMORY_INDEX.read_text(encoding="utf-8").strip()
    return text if text else ""
def read_memory_file(filename: str) -> str | None:
    """读单个记忆文件的完整内容。"""
    path = MEMORY_DIR / filename
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")
def list_memory_files() -> list[dict]:
    """列出所有记忆文件的元数据（名称、描述、类型、正文）。"""
    result = []
    for f in sorted(MEMORY_DIR.glob("*.md")):
        if f.name == "MEMORY.md":
            continue
        raw = f.read_text(encoding="utf-8")
        meta, body = _parse_memory_frontmatter(raw)
        result.append({
            "filename": f.name,
            "name": meta.get("name", f.stem),
            "description": meta.get("description", ""),
            "type": meta.get("type", "user"),
            "body": body,
        })
    return result
def select_relevant_memories(messages: list, max_items: int = 5) -> list[str]:
    """用 LLM 侧查询选出跟当前对话最相关的记忆文件名。
    失败时降级为关键词匹配。"""
    files = list_memory_files()
    if not files:
        return []

    # 收集最近的用户文本作为上下文
    recent_texts = []
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, list):
                content = " ".join(
                    str(getattr(b, "text", "")) for b in content
                    if getattr(b, "type", None) == "text"
                )
            if isinstance(content, str):
                recent_texts.append(content)
            if len(recent_texts) >= 3:
                break
    recent = " ".join(reversed(recent_texts))[:2000]

    if not recent.strip():
        return []

    # 构建记忆目录供 LLM 选择
    catalog_lines = [f"{i}: {f['name']} — {f['description']}" for i, f in enumerate(files)]
    catalog = "\n".join(catalog_lines)

    prompt = (
        "根据最近的对话和下面的记忆目录，选出明显相关的记忆的索引。"
        "只返回 JSON 整数数组，如 [0, 3]。都不相关则返回 []。\n\n"
        f"最近对话：\n{recent}\n\n"
        f"记忆目录：\n{catalog}"
    )

    try:
        response = client.messages.create(
            model=PRIMARY_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
        )
        text = extract_text(response.content).strip()
        match = re.search(r'\[.*?\]', text, re.DOTALL)
        if match:
            indices = json.loads(match.group())
            selected = []
            for idx in indices:
                if isinstance(idx, int) and 0 <= idx < len(files):
                    selected.append(files[idx]["filename"])
                    if len(selected) >= max_items:
                        break
            return selected
    except Exception:
        pass

    # 降级：关键词匹配 name + description
    keywords = [w.lower() for w in recent.split() if len(w) > 3]
    selected = []
    for f in files:
        text = (f["name"] + " " + f["description"]).lower()
        if any(kw in text for kw in keywords):
            selected.append(f["filename"])
            if len(selected) >= max_items:
                break
    return selected
def load_memories(messages: list) -> str:
    """加载相关记忆内容，包装为 <relevant_memories> 标签。"""
    selected_files = select_relevant_memories(messages)
    if not selected_files:
        return ""

    parts = ["<relevant_memories>"]
    for filename in selected_files:
        content = read_memory_file(filename)
        if content:
            parts.append(content)
    parts.append("</relevant_memories>")
    return "\n\n".join(parts)
def extract_memories(messages: list):
    """从最近对话中提取新记忆，写入 .memory/。每轮结束后调用。"""
    # 收集最近 10 条消息的文本
    dialogue_parts = []
    for msg in messages[-10:]:
        role = msg.get("role", "?")
        content = msg.get("content", "")
        if isinstance(content, list):
            content = " ".join(
                str(getattr(b, "text", "")) for b in content
                if getattr(b, "type", None) == "text"
            )
        if isinstance(content, str) and content.strip():
            dialogue_parts.append(f"{role}: {content}")
    dialogue = "\n".join(dialogue_parts)

    if not dialogue.strip():
        return

    # 检查已有记忆，避免重复
    existing = list_memory_files()
    existing_desc = "\n".join(
        f"- {m['name']}: {m['description']}" for m in existing
    ) if existing else "（无）"

    prompt = (
        "从以下对话中提取用户偏好、约束或项目事实。\n"
        "返回 JSON 数组。每项：{name, type, description, body}。\n"
        "- name: 短的 kebab-case 标识符（如 'user-preference-tabs'）\n"
        "- type: 类型，'user'（用户偏好）/ 'feedback'（行事指引）/ "
        "'project'（项目事实）/ 'reference'（外部指针）\n"
        "- description: 一行摘要，用于索引查找\n"
        "- body: markdown 格式的完整详情\n"
        "如果没有新内容或已有记忆已覆盖，返回 []。\n\n"
        f"已有记忆：\n{existing_desc}\n\n"
        f"对话：\n{dialogue[:4000]}"
    )

    try:
        response = client.messages.create(
            model=PRIMARY_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=800,
        )
        text = extract_text(response.content).strip()
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if not match:
            return
        items = json.loads(match.group())
        if not items:
            return
        count = 0
        for mem in items:
            name = mem.get("name", f"memory_{int(time.time())}")
            mem_type = mem.get("type", "user")
            desc = mem.get("description", "")
            body = mem.get("body", "")
            if desc and body:
                write_memory_file(name, mem_type, desc, body)
                count += 1
        if count:
            safe_print(f"\n\033[33m[记忆: 提取了 {count} 条新记忆]\033[0m")
    except Exception:
        pass
def consolidate_memories():
    """记忆文件数达到阈值时，让 LLM 去重合并、删除过时记忆。"""
    files = list_memory_files()
    if len(files) < CONSOLIDATE_THRESHOLD:
        return

    catalog = "\n\n".join(
        f"## {f['filename']}\nname: {f['name']}\ndescription: {f['description']}\n{f['body']}"
        for f in files
    )

    prompt = (
        "整理以下记忆文件。规则：\n"
        "1. 合并内容重复的记忆\n"
        "2. 删除已过时或被新记忆覆盖的\n"
        "3. 总数控制在 30 条以内\n"
        "4. 优先保留用户偏好类记忆\n"
        "返回 JSON 数组。每项：{name, type, description, body}。\n\n"
        f"{catalog[:16000]}"
    )

    try:
        response = client.messages.create(
            model=PRIMARY_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=3000,
        )
        text = extract_text(response.content).strip()
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if not match:
            return
        items = json.loads(match.group())

        # 删除所有旧记忆文件（保留 MEMORY.md）
        for f in MEMORY_DIR.glob("*.md"):
            if f.name != "MEMORY.md":
                f.unlink()

        for mem in items:
            name = mem.get("name", f"memory_{int(time.time())}")
            mem_type = mem.get("type", "user")
            desc = mem.get("description", "")
            body = mem.get("body", "")
            if desc and body:
                write_memory_file(name, mem_type, desc, body)

        safe_print(f"\n\033[33m[记忆: 整理 {len(files)} → {len(items)} 条]\033[0m")
    except Exception:
        pass
