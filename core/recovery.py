"""错误恢复系统 — s11"""
import time, random
from config import safe_print,  PRIMARY_MODEL, FALLBACK_MODEL

ESCALATED_MAX_TOKENS = 64000           # max_tokens 升级目标
DEFAULT_MAX_TOKENS = 8000              # 默认输出 token 上限
MAX_RECOVERY_RETRIES = 3               # 续写最多尝试次数
MAX_RETRIES = 10                       # 429/529 最多重试次数
BASE_DELAY_MS = 500                    # 指数退避基础延迟（毫秒）
MAX_CONSECUTIVE_529 = 3                # 连续 529 后切换备用模型
CONTINUATION_PROMPT = (
    "输出 token 限制已达。直接继续——不要道歉，不要复述。从中断处接着写。"
)
class RecoveryState:
    """追踪一轮 agent_loop 中的恢复尝试状态。"""
    def __init__(self):
        self.has_escalated = False              # 是否已从 8K 升级到 64K
        self.recovery_count = 0                  # 续写次数（最多 3）
        self.consecutive_529 = 0                 # 连续 529 过载计数
        self.has_attempted_reactive_compact = False  # 是否已尝试应急压缩
        self.current_model = PRIMARY_MODEL       # 当前使用的模型（529 后可切换）
def retry_delay(attempt, retry_after=None):
    """指数退避 + 随机抖动。Retry-After header 优先。

    公式: min(500 × 2^attempt, 32000) / 1000 秒 + 0~25% 随机抖动。
    """
    if retry_after:
        return retry_after
    base = min(BASE_DELAY_MS * (2 ** attempt), 32000) / 1000
    jitter = random.uniform(0, base * 0.25)
    return base + jitter
def is_prompt_too_long_error(e: Exception) -> bool:
    """判断异常是否属于上下文超限（兼容多种 API 的错误消息格式）。"""
    msg = str(e).lower()
    return (("prompt" in msg and "long" in msg)
            or "prompt_is_too_long" in msg
            or "context_length_exceeded" in msg
            or "max_context_window" in msg)
def with_retry(fn, state: RecoveryState):
    """对 429/529 瞬态错误做指数退避重试。

    非瞬态错误（如 prompt_too_long）直接往外抛，
    交给外层 try/except 处理。"""
    for attempt in range(MAX_RETRIES):
        try:
            result = fn()
            state.consecutive_529 = 0  # 调用成功，重置计数器
            return result
        except Exception as e:
            name = type(e).__name__
            msg = str(e).lower()

            # 429 限流 → 指数退避
            if "ratelimit" in name.lower() or "429" in msg:
                delay = retry_delay(attempt)
                safe_print(f"  \033[33m[429 限流] 重试 {attempt+1}/{MAX_RETRIES},"
                      f" 等待 {delay:.1f}s\033[0m")
                time.sleep(delay)
                continue

            # 529 过载 → 指数退避 + 可能切换备用模型
            if "overloaded" in name.lower() or "529" in msg or "overloaded" in msg:
                state.consecutive_529 += 1
                if state.consecutive_529 >= MAX_CONSECUTIVE_529:
                    if FALLBACK_MODEL:
                        state.current_model = FALLBACK_MODEL
                        state.consecutive_529 = 0
                        safe_print(f"  \033[31m[529 x{MAX_CONSECUTIVE_529}]"
                              f" 切换到备用模型 {FALLBACK_MODEL}\033[0m")
                    else:
                        state.consecutive_529 = 0
                        safe_print(f"  \033[31m[529 x{MAX_CONSECUTIVE_529}]"
                              f" 未配置 FALLBACK_MODEL_ID，继续重试\033[0m")
                delay = retry_delay(attempt)
                safe_print(f"  \033[33m[529 过载] 重试 {attempt+1}/{MAX_RETRIES},"
                      f" 等待 {delay:.1f}s\033[0m")
                time.sleep(delay)
                continue

            # 非瞬态错误 → 往外抛给外层 try/except
            raise

    raise RuntimeError(f"超过最大重试次数 ({MAX_RETRIES})")
