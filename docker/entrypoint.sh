#!/bin/bash
set -e

# 可选：使用单一挂载点（适合 ClawCloud Run 这类平台）
# 需要显式开启：USE_DATA_DIR=true
# 开启后会把 /app/config 与 /app/output 映射到 $DATA_DIR 下，确保重建/迁移后数据仍在。
USE_DATA_DIR="${USE_DATA_DIR:-false}"
DATA_DIR="${DATA_DIR:-/data}"
if [ "$USE_DATA_DIR" = "true" ] && [ -d "$DATA_DIR" ]; then
    mkdir -p "$DATA_DIR/config" "$DATA_DIR/output"

    # 将镜像内置目录替换为指向挂载目录的 symlink
    if [ -d "/app/config" ] && [ ! -L "/app/config" ]; then
        if [ -z "$(ls -A /app/config 2>/dev/null)" ]; then
            rmdir /app/config || true
        else
            mv /app/config "/app/config.image.$(date +%s)" || true
        fi
    fi
    if [ -d "/app/output" ] && [ ! -L "/app/output" ]; then
        if [ -z "$(ls -A /app/output 2>/dev/null)" ]; then
            rmdir /app/output || true
        else
            mv /app/output "/app/output.image.$(date +%s)" || true
        fi
    fi

    [ -e "/app/config" ] || ln -s "$DATA_DIR/config" /app/config
    [ -e "/app/output" ] || ln -s "$DATA_DIR/output" /app/output

    # 首次启动：如果挂载目录未放置配置文件，复制项目默认配置
    if [ -d "/app/config.default" ]; then
        if [ ! -f "/app/config/config.yaml" ] && [ -f "/app/config.default/config.yaml" ]; then
            cp -f "/app/config.default/config.yaml" "/app/config/config.yaml"
        fi
        if [ ! -f "/app/config/frequency_words.txt" ] && [ -f "/app/config.default/frequency_words.txt" ]; then
            cp -f "/app/config.default/frequency_words.txt" "/app/config/frequency_words.txt"
        fi
    fi
fi

# 检查配置文件
if [ ! -f "/app/config/config.yaml" ] || [ ! -f "/app/config/frequency_words.txt" ]; then
    echo "❌ 配置文件缺失"
    exit 1
fi

# 保存环境变量
env >> /etc/environment

case "${RUN_MODE:-cron}" in
"once")
    echo "🔄 单次执行"
    exec /usr/local/bin/python -m trendradar
    ;;
"cron")
    # 生成 crontab
    echo "${CRON_SCHEDULE:-*/30 * * * *} cd /app && /usr/local/bin/python -m trendradar" > /tmp/crontab
    
    echo "📅 生成的crontab内容:"
    cat /tmp/crontab

    if ! /usr/local/bin/supercronic -test /tmp/crontab; then
        echo "❌ crontab格式验证失败"
        exit 1
    fi

    # 立即执行一次（如果配置了）
    if [ "${IMMEDIATE_RUN:-false}" = "true" ]; then
        echo "▶️ 立即执行一次"
        /usr/local/bin/python -m trendradar
    fi

    # 启动 Web 服务器（如果配置了）
    ENABLE_WEBSERVER_EFFECTIVE="${ENABLE_WEBSERVER:-}"
    if [ -z "$ENABLE_WEBSERVER_EFFECTIVE" ] && [ -n "${PORT:-}" ]; then
        ENABLE_WEBSERVER_EFFECTIVE="true"
    fi
    ENABLE_WEBSERVER_EFFECTIVE="${ENABLE_WEBSERVER_EFFECTIVE:-false}"

    if [ "$ENABLE_WEBSERVER_EFFECTIVE" = "true" ]; then
        echo "🌐 启动 Web 服务器..."
        /usr/local/bin/python manage.py start_webserver
    else
        echo "ℹ️ 未启用 Web 服务器 (ENABLE_WEBSERVER=${ENABLE_WEBSERVER:-<unset>}, PORT=${PORT:-<unset>})"
    fi

    echo "⏰ 启动supercronic: ${CRON_SCHEDULE:-*/30 * * * *}"
    echo "🎯 supercronic 将作为 PID 1 运行"

    exec /usr/local/bin/supercronic -passthrough-logs /tmp/crontab
    ;;
*)
    exec "$@"
    ;;
esac
