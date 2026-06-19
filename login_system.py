"""
用户登录系统 - 后端实现
包含：用户注册、登录、JWT 令牌验证、用户信息接口
"""
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps

import bcrypt
import jwt
from flask import Flask, jsonify, request

# 配置
SECRET_KEY = os.environ.get("SECRET_KEY", "default-secret-key-change-in-production")
JWT_EXPIRATION_HOURS = 24
DATA_FILE = "users.json"
app = Flask(__name__)


def load_users():
    """从本地文件加载用户数据"""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_users(users):
    """保存用户数据到本地文件"""
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2, ensure_ascii=False)


def hash_password(password: str) -> str:
    """使用 bcrypt 哈希密码"""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def check_password(password: str, hashed: str) -> bool:
    """验证密码"""
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


def create_token(user_id: str) -> str:
    """生成 JWT 令牌"""
    payload = {
        "user_id": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRATION_HOURS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def token_required(f):
    """JWT 验证装饰器"""

    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        auth_header = request.headers.get("Authorization")

        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]

        if not token:
            return jsonify({"error": "Token is missing"}), 401

        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            current_user_id = payload["user_id"]
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token has expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401

        return f(current_user_id, *args, **kwargs)

    return decorated


# ========== API 路由 ==========


@app.route("/api/health", methods=["GET"])
def health_check():
    """健康检查接口"""
    return jsonify({"status": "ok", "service": "login-system", "version": "1.0.0"})


@app.route("/api/auth/register", methods=["POST"])
def register():
    """用户注册"""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body is required"}), 400

    username = data.get("username", "").strip()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    # 参数验证
    if not username or not email or not password:
        return jsonify({"error": "Username, email and password are required"}), 400

    if len(username) < 3 or len(username) > 50:
        return jsonify({"error": "Username must be between 3 and 50 characters"}), 400

    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400

    if "@" not in email or "." not in email:
        return jsonify({"error": "Invalid email format"}), 400

    users = load_users()

    # 检查重复
    for uid, user in users.items():
        if user["username"] == username:
            return jsonify({"error": "Username already exists"}), 409
        if user["email"] == email:
            return jsonify({"error": "Email already registered"}), 409

    # 创建用户
    user_id = str(uuid.uuid4())
    users[user_id] = {
        "id": user_id,
        "username": username,
        "email": email,
        "password_hash": hash_password(password),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    save_users(users)

    token = create_token(user_id)
    return (
        jsonify(
            {
                "message": "User registered successfully",
                "user": {"id": user_id, "username": username, "email": email},
                "token": token,
            }
        ),
        201,
    )


@app.route("/api/auth/login", methods=["POST"])
def login():
    """用户登录"""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body is required"}), 400

    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    users = load_users()

    # 查找用户
    found_user = None
    found_id = None
    for uid, user in users.items():
        if user["username"] == username:
            found_user = user
            found_id = uid
            break

    if not found_user:
        return jsonify({"error": "Invalid username or password"}), 401

    if not check_password(password, found_user["password_hash"]):
        return jsonify({"error": "Invalid username or password"}), 401

    # 更新最后登录时间
    found_user["last_login_at"] = datetime.now(timezone.utc).isoformat()
    save_users(users)

    token = create_token(found_id)
    return jsonify(
        {
            "message": "Login successful",
            "user": {
                "id": found_id,
                "username": found_user["username"],
                "email": found_user["email"],
            },
            "token": token,
        }
    )


@app.route("/api/auth/profile", methods=["GET"])
@token_required
def get_profile(current_user_id):
    """获取当前用户信息（需要认证）"""
    users = load_users()
    user = users.get(current_user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    return jsonify(
        {
            "user": {
                "id": user["id"],
                "username": user["username"],
                "email": user["email"],
                "created_at": user["created_at"],
                "last_login_at": user.get("last_login_at"),
            }
        }
    )


@app.route("/api/auth/refresh", methods=["POST"])
@token_required
def refresh_token(current_user_id):
    """刷新 JWT 令牌"""
    users = load_users()
    if current_user_id not in users:
        return jsonify({"error": "User not found"}), 404

    new_token = create_token(current_user_id)
    return jsonify({"token": new_token})


@app.route("/api/auth/logout", methods=["POST"])
@token_required
def logout(current_user_id):
    """登出接口（客户端应丢弃令牌）"""
    return jsonify({"message": "Logged out successfully. Please discard your token."})


# ========== 启动入口 ==========

if __name__ == "__main__":
    print("=" * 50)
    print("  用户登录系统 v1.0")
    print("  Running on http://127.0.0.1:5000")
    print("  API 文档:")
    print("    POST /api/auth/register  - 注册")
    print("    POST /api/auth/login     - 登录")
    print("    GET  /api/auth/profile   - 获取用户信息 (需 Bearer Token)")
    print("    POST /api/auth/refresh   - 刷新令牌 (需 Bearer Token)")
    print("    POST /api/auth/logout    - 登出 (需 Bearer Token)")
    print("    GET  /api/health         - 健康检查")
    print("=" * 50)
    app.run(host="127.0.0.1", port=5000, debug=True)
