# ============================================================
# mes1 Web Agent —— 后端镜像（Dockerfile）
# 作用：把 Python 引擎 + FastAPI 服务打包成"可随处运行的镜像"
# 类比：这是"菜谱"，docker build 照它做出"镜像"(image)
# ============================================================

# 1) 基础镜像：官方 Python 3.11 精简版（slim 体积更小、够用）
FROM python:3.11-slim

# 2) 容器内的工作目录（后续命令都在这个目录下执行）
WORKDIR /app

# 3) 先只复制"依赖清单"再安装 —— 利用 Docker 层缓存：
#    只要依赖不变，这一层就不必重装，以后构建飞快
COPY requirements.txt ./
COPY api/requirements.txt ./api/requirements.txt

#    只装"运行时"依赖（刻意不装 pytest/ruff 等开发依赖，镜像更小）
RUN pip install --no-cache-dir -r api/requirements.txt \
    && pip install --no-cache-dir \
       "anthropic>=0.100.0" \
       "python-dotenv>=1.0.0" \
       "pyyaml>=6.0"

# 4) 再复制全部项目源码（这一步变化最频繁，放最后、改动不触发重装依赖）
COPY . .

# 5) 声明容器对外暴露的端口（FastAPI 默认 5000）
EXPOSE 5000

# 6) 启动命令：用 uvicorn 跑 FastAPI
#    --host 0.0.0.0 让容器外也能访问（容器化必写，否则只能容器内自访问）
#    模型/密钥通过环境变量传入（见下方"怎么跑"），不写死在镜像里
CMD ["sh", "-c", "python -m uvicorn api.server:app --host 0.0.0.0 --port 5000"]
