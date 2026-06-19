"""MessageBus — s15"""
import json, time
from config import safe_print, RUNTIME_DIR

MAILBOX_DIR = RUNTIME_DIR / "mailboxes"
MAILBOX_DIR.mkdir(exist_ok=True)
class MessageBus:
    """文件收件箱：发消息 = append JSONL 行，读消息 = 读+删（消费式）。
    教学版无文件锁；真实 CC 用 proper-lockfile。"""

    def send(self, from_agent: str, to_agent: str, content: str,
             msg_type: str = "message", metadata: dict = None):
        msg = {"from": from_agent, "to": to_agent,
               "content": content, "type": msg_type,
               "ts": time.time(), "metadata": metadata or {}}
        inbox = MAILBOX_DIR / f"{to_agent}.jsonl"
        with open(inbox, "a", encoding="utf-8") as f:
            f.write(json.dumps(msg, ensure_ascii=False) + "\n")
        safe_print(f"  \033[33m[消息总线] {from_agent} → {to_agent}: "
              f"{content[:50]}\033[0m")

    def read_inbox(self, agent: str) -> list[dict]:
        """读取并清空收件箱（消费式）。"""
        inbox = MAILBOX_DIR / f"{agent}.jsonl"
        if not inbox.exists():
            return []
        msgs = [json.loads(line) for line in inbox.read_text(encoding="utf-8").splitlines()
                if line.strip()]
        inbox.unlink()
        return msgs
BUS = MessageBus()
active_teammates: dict[str, bool] = {}
