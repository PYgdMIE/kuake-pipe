# kuake-pipe Docker image
#
# 用途:headless 跑 kuake auto / serve, 适合服务器 / CI / 容器编排。
# 默认 entrypoint 是 kuake CLI, 不带参数 = kuake --help。
#
# 用法:
#   docker run --rm -v $HOME/.kuake:/root/.kuake ghcr.io/pygdmie/kuake-pipe:latest --help
#   docker run --rm -p 8765:8765 -v $HOME/.kuake:/root/.kuake \
#     ghcr.io/pygdmie/kuake-pipe:latest serve --host 0.0.0.0
#
# Volume:
#   - /root/.kuake  → storage_state.json + config + credentials + jobs/
#
# Caveats:
#   - Quark / AutoDL 扫码登录 (kuake init) 需要可见浏览器, 容器内默认 headless
#     ⇒ 推荐宿主机先跑一次 kuake init (扫两次码), 然后把 ~/.kuake mount 进去
#   - 之后 kuake init --headless / kuake auto / kuake serve 都能容器里跑

FROM python:3.12-slim

LABEL org.opencontainers.image.title="kuake-pipe"
LABEL org.opencontainers.image.description="本地 → 夸克 → AutoDL 全自动 + 抢卡 + Web UI"
LABEL org.opencontainers.image.source="https://github.com/PYgdMIE/kuake-pipe"
LABEL org.opencontainers.image.licenses="MIT"

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-browsers

# Playwright Chromium 运行时依赖 (官方文档列表 + 中文字体)
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl gnupg \
        libnss3 libnspr4 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 \
        libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 \
        libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2 \
        libatspi2.0-0 \
        fonts-noto-cjk \
        && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先复制 pyproject + readme 利用 docker cache
COPY pyproject.toml README.md ./
COPY src/ ./src/

RUN pip install --upgrade pip \
    && pip install . \
    && python -m playwright install chromium

# 默认 entrypoint = kuake CLI
ENTRYPOINT ["kuake"]
CMD ["--help"]
