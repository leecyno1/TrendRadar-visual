# coding=utf-8
import os
import re
import sqlite3
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
import io
import contextlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from trendradar.web.config_store import ConfigStore


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_int(value: Optional[str], default: int, *, min_value: int, max_value: int) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return max(min_value, min(max_value, parsed))


def _safe_str(value: Optional[str]) -> str:
    return (value or "").strip()


@dataclass(frozen=True)
class Paths:
    output_dir: Path
    config_path: Path
    frequency_words_path: Path


def _resolve_paths() -> Paths:
    config_path = Path(os.environ.get("CONFIG_PATH", "config/config.yaml"))
    frequency_words_path = Path(os.environ.get("FREQUENCY_WORDS_PATH", "config/frequency_words.txt"))
    output_dir = Path(os.environ.get("OUTPUT_DIR", "output"))

    # Docker 运行时默认 /app/output，更符合挂载习惯
    if not output_dir.exists() and Path("/app/output").exists():
        output_dir = Path("/app/output")

    return Paths(
        output_dir=output_dir,
        config_path=config_path,
        frequency_words_path=frequency_words_path,
    )


PATHS = _resolve_paths()
TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "").strip()

CONFIG_STORE = ConfigStore(
    config_path=PATHS.config_path,
    frequency_words_path=PATHS.frequency_words_path,
    default_config_candidates=(
        Path("/app/config.default/config.yaml"),
        Path("config/config.yaml"),
    ),
    default_words_candidates=(
        Path("/app/config.default/frequency_words.txt"),
        Path("config/frequency_words.txt"),
    ),
)

SAFE_OUTPUT_EXTENSIONS = {
    ".html",
    ".txt",
    ".json",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".svg",
    ".css",
    ".js",
}

DATE_DIR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_OUTPUT_DIR_CACHE: Dict[str, Any] = {"config_mtime": None, "dir": None}


def _base_dir() -> Path:
    if Path("/app").exists():
        return Path("/app")
    return Path.cwd()


def get_output_dir() -> Path:
    """
    输出目录解析优先级：
    1) 环境变量 OUTPUT_DIR（强制指定）
    2) config.yaml 的 storage.local.data_dir（相对路径基于 /app 或 cwd）
    3) /app/output（容器常见）
    4) ./output
    """
    env_dir = os.environ.get("OUTPUT_DIR", "").strip()
    if env_dir:
        return Path(env_dir)

    config_path = PATHS.config_path
    try:
        mtime = config_path.stat().st_mtime if config_path.exists() else None
    except Exception:
        mtime = None

    if _OUTPUT_DIR_CACHE["dir"] is not None and _OUTPUT_DIR_CACHE["config_mtime"] == mtime:
        return _OUTPUT_DIR_CACHE["dir"]

    data_dir = "output"
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = yaml.safe_load(f) or {}
            storage = config_data.get("storage", {}) if isinstance(config_data, dict) else {}
            local = storage.get("local", {}) if isinstance(storage, dict) else {}
            raw = local.get("data_dir", "output") if isinstance(local, dict) else "output"
            if isinstance(raw, str) and raw.strip():
                data_dir = raw.strip()
        except Exception:
            data_dir = "output"

    out = Path(data_dir)
    if not out.is_absolute():
        out = _base_dir() / out

    if not out.exists() and Path("/app/output").exists():
        out = Path("/app/output")

    _OUTPUT_DIR_CACHE["config_mtime"] = mtime
    _OUTPUT_DIR_CACHE["dir"] = out
    return out


def _require_admin(request: Request) -> None:
    if not ADMIN_TOKEN:
        return
    token = request.headers.get("x-admin-token", "").strip()
    if token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Missing or invalid admin token")


def _db_path_for_date(date_str: str) -> Path:
    if not DATE_DIR_RE.match(date_str):
        raise HTTPException(status_code=400, detail="Invalid date format, expected YYYY-MM-DD")
    db_path = get_output_dir() / date_str / "news.db"
    if not db_path.exists():
        raise HTTPException(status_code=404, detail=f"news.db not found for date {date_str}")
    return db_path


def _connect_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _scan_report_files() -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    output_dir = get_output_dir()
    if not output_dir.exists():
        return items

    # 单独收集 output/index.html（每日汇总会复制）
    root_index = output_dir / "index.html"
    if root_index.exists():
        stat = root_index.stat()
        items.append(
            {
                "id": "output/index.html",
                "label": "最新汇总（index.html）",
                "relpath": "index.html",
                "date": None,
                "mtime": stat.st_mtime,
                "size": stat.st_size,
            }
        )

    # 收集各日期下 html/*.html
    for date_dir in sorted(output_dir.iterdir(), reverse=True):
        if not date_dir.is_dir():
            continue
        if not DATE_DIR_RE.match(date_dir.name):
            continue
        html_dir = date_dir / "html"
        if not html_dir.exists():
            continue
        for html_file in sorted(html_dir.glob("*.html")):
            stat = html_file.stat()
            relpath = html_file.relative_to(output_dir).as_posix()
            items.append(
                {
                    "id": relpath,
                    "label": f"{date_dir.name} / {html_file.name}",
                    "relpath": relpath,
                    "date": date_dir.name,
                    "mtime": stat.st_mtime,
                    "size": stat.st_size,
                }
            )

    items.sort(key=lambda x: x["mtime"], reverse=True)
    return items


def _read_text_file(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _write_text_file_with_backup(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = path.with_suffix(path.suffix + f".bak.{ts}")
        backup_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    path.write_text(content, encoding="utf-8")


app = FastAPI(title="TrendRadar Dashboard", version="0.1.0")


@app.get("/api/health")
def health() -> Dict[str, Any]:
    return {
        "ok": True,
        "time": _now_iso(),
        "paths": {
            "output_dir": str(get_output_dir()),
            "config_path": str(PATHS.config_path),
            "frequency_words_path": str(PATHS.frequency_words_path),
        },
        "admin_token_required": bool(ADMIN_TOKEN),
    }


@app.get("/", response_class=HTMLResponse)
def home(request: Request) -> Any:
    return TEMPLATES.TemplateResponse(
        request,
        "home.html",
        {
            "title": "TrendRadar",
        },
    )


@app.get("/index.html")
def legacy_index() -> Any:
    candidate = get_output_dir() / "index.html"
    if candidate.exists():
        return FileResponse(str(candidate))
    raise HTTPException(status_code=404, detail="index.html not found")


@app.get("/reports", response_class=HTMLResponse)
def reports_page(request: Request) -> Any:
    return TEMPLATES.TemplateResponse(request, "reports.html", {"title": "Reports"})


@app.get("/browse", response_class=HTMLResponse)
def browse_page(request: Request) -> Any:
    return TEMPLATES.TemplateResponse(request, "browse.html", {"title": "Browse"})


@app.get("/manage", response_class=HTMLResponse)
def manage_page(request: Request) -> Any:
    return TEMPLATES.TemplateResponse(
        request,
        "manage.html",
        {"title": "Manage", "admin_token_required": bool(ADMIN_TOKEN)},
    )


@app.get("/output/{relpath:path}")
def output_file(relpath: str) -> Any:
    relpath = relpath.strip().lstrip("/")
    if not relpath:
        raise HTTPException(status_code=404, detail="Not found")

    output_dir = get_output_dir()
    candidate = (output_dir / relpath).resolve()
    output_root = output_dir.resolve()
    if output_root not in candidate.parents and candidate != output_root:
        raise HTTPException(status_code=400, detail="Invalid path")

    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=404, detail="Not found")

    if candidate.suffix.lower() not in SAFE_OUTPUT_EXTENSIONS:
        raise HTTPException(status_code=403, detail="File type not allowed")

    return FileResponse(str(candidate))


@app.get("/api/reports")
def list_reports() -> List[Dict[str, Any]]:
    return _scan_report_files()


@app.get("/api/reports/latest")
def latest_report() -> Dict[str, Any]:
    reports = _scan_report_files()
    if not reports:
        raise HTTPException(status_code=404, detail="No reports found")
    return reports[0]


@app.get("/api/dates")
def list_dates() -> List[str]:
    output_dir = get_output_dir()
    if not output_dir.exists():
        return []
    dates = []
    for p in output_dir.iterdir():
        if p.is_dir() and DATE_DIR_RE.match(p.name):
            dates.append(p.name)
    dates.sort(reverse=True)
    return dates


@app.get("/api/platforms")
def list_platforms(date: str) -> List[Dict[str, Any]]:
    db_path = _db_path_for_date(date)
    conn = _connect_db(db_path)
    try:
        rows = conn.execute("SELECT id, name, is_active, updated_at FROM platforms ORDER BY id").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@app.get("/api/news")
def search_news(
    date: str,
    q: Optional[str] = None,
    platform_id: Optional[str] = None,
    limit: Optional[str] = None,
    offset: Optional[str] = None,
    sort: Optional[str] = None,
) -> Dict[str, Any]:
    db_path = _db_path_for_date(date)
    query = _safe_str(q)
    platform_id = _safe_str(platform_id)
    limit_i = _safe_int(limit, 50, min_value=1, max_value=200)
    offset_i = _safe_int(offset, 0, min_value=0, max_value=1000000)
    sort = _safe_str(sort) or "last_crawl_time_desc"

    where = []
    params: List[Any] = []

    if platform_id:
        where.append("n.platform_id = ?")
        params.append(platform_id)

    if query:
        where.append("n.title LIKE ?")
        params.append(f"%{query}%")

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

    sort_map = {
        "last_crawl_time_desc": "n.last_crawl_time DESC",
        "rank_asc": "n.rank ASC",
        "crawl_count_desc": "n.crawl_count DESC",
    }
    order_sql = sort_map.get(sort, sort_map["last_crawl_time_desc"])

    conn = _connect_db(db_path)
    try:
        total = conn.execute(
            f"SELECT COUNT(1) AS c FROM news_items n {where_sql}",
            params,
        ).fetchone()["c"]

        rows = conn.execute(
            f"""
            SELECT
              n.id,
              n.title,
              n.platform_id,
              p.name AS platform_name,
              n.rank,
              n.url,
              n.mobile_url,
              n.first_crawl_time,
              n.last_crawl_time,
              n.crawl_count
            FROM news_items n
            LEFT JOIN platforms p ON p.id = n.platform_id
            {where_sql}
            ORDER BY {order_sql}
            LIMIT ? OFFSET ?
            """,
            [*params, limit_i, offset_i],
        ).fetchall()

        return {
            "date": date,
            "q": query,
            "platform_id": platform_id or None,
            "sort": sort,
            "limit": limit_i,
            "offset": offset_i,
            "total": total,
            "items": [dict(r) for r in rows],
        }
    finally:
        conn.close()


@app.get("/api/news/{news_id}")
def get_news_item(date: str, news_id: int) -> Dict[str, Any]:
    db_path = _db_path_for_date(date)
    conn = _connect_db(db_path)
    try:
        row = conn.execute(
            """
            SELECT
              n.*,
              p.name AS platform_name
            FROM news_items n
            LEFT JOIN platforms p ON p.id = n.platform_id
            WHERE n.id = ?
            """,
            [news_id],
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Not found")
        return dict(row)
    finally:
        conn.close()


@app.get("/api/news/{news_id}/rank-history")
def get_rank_history(date: str, news_id: int, limit: Optional[str] = None) -> Dict[str, Any]:
    db_path = _db_path_for_date(date)
    limit_i = _safe_int(limit, 200, min_value=1, max_value=2000)
    conn = _connect_db(db_path)
    try:
        rows = conn.execute(
            """
            SELECT rank, crawl_time, created_at
            FROM rank_history
            WHERE news_item_id = ?
            ORDER BY crawl_time DESC
            LIMIT ?
            """,
            [news_id, limit_i],
        ).fetchall()
        return {"date": date, "news_id": news_id, "items": [dict(r) for r in rows]}
    finally:
        conn.close()


@app.get("/api/admin/config")
def admin_get_config(request: Request) -> Any:
    _require_admin(request)
    return JSONResponse({"path": str(PATHS.config_path), "content": _read_text_file(PATHS.config_path)})


@app.put("/api/admin/config")
async def admin_put_config(request: Request) -> Any:
    _require_admin(request)
    payload = await request.json()
    content = payload.get("content")
    if not isinstance(content, str):
        raise HTTPException(status_code=400, detail="content must be a string")

    try:
        parsed = yaml.safe_load(content)  # validate YAML
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {e}")
    if parsed is None:
        raise HTTPException(status_code=400, detail="YAML is empty")
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="Config must be a YAML mapping (object)")

    try:
        _write_text_file_with_backup(PATHS.config_path, content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Write failed: {e}")

    return JSONResponse({"ok": True, "path": str(PATHS.config_path)})


@app.get("/api/admin/config/parsed")
def admin_get_config_parsed(request: Request) -> Any:
    _require_admin(request)
    return JSONResponse(
        {
            "path": str(PATHS.config_path),
            "config": CONFIG_STORE.get_config_plain(),
        }
    )


@app.put("/api/admin/config/patch")
async def admin_patch_config(request: Request) -> Any:
    _require_admin(request)
    payload = await request.json()
    patch = payload.get("patch")
    if not isinstance(patch, dict):
        raise HTTPException(status_code=400, detail="patch must be an object")
    try:
        result = CONFIG_STORE.patch_config(patch)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return JSONResponse({"ok": True, **result})


@app.post("/api/admin/config/reset")
def admin_reset_config(request: Request) -> Any:
    _require_admin(request)
    try:
        result = CONFIG_STORE.reset_config_to_default()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return JSONResponse({"ok": True, **result})


@app.get("/api/admin/frequency-words")
def admin_get_frequency_words(request: Request) -> Any:
    _require_admin(request)
    return JSONResponse(
        {"path": str(PATHS.frequency_words_path), "content": _read_text_file(PATHS.frequency_words_path)}
    )


@app.put("/api/admin/frequency-words")
async def admin_put_frequency_words(request: Request) -> Any:
    _require_admin(request)
    payload = await request.json()
    content = payload.get("content")
    if not isinstance(content, str):
        raise HTTPException(status_code=400, detail="content must be a string")

    try:
        _write_text_file_with_backup(PATHS.frequency_words_path, content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Write failed: {e}")

    return JSONResponse({"ok": True, "path": str(PATHS.frequency_words_path)})


@app.post("/api/admin/frequency-words/reset")
def admin_reset_frequency_words(request: Request) -> Any:
    _require_admin(request)
    try:
        result = CONFIG_STORE.reset_words_to_default()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return JSONResponse({"ok": True, **result})


@app.post("/api/admin/actions/trigger-crawl")
def admin_trigger_crawl(request: Request) -> Any:
    _require_admin(request)
    # 在容器里跑一次 crawler（异步）
    try:
        subprocess.Popen(
            [os.environ.get("PYTHON", "python"), "-m", "trendradar"],
            cwd="/app" if Path("/app").exists() else None,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start crawl: {e}")
    return {"ok": True, "started_at": _now_iso()}


@app.get("/api/admin/system")
def admin_system_status(request: Request) -> Any:
    _require_admin(request)
    reports = _scan_report_files()
    return {
        "ok": True,
        "time": _now_iso(),
        "output_dir": str(get_output_dir()),
        "reports_count": len(reports),
        "latest_report": reports[0] if reports else None,
    }


def _redact_value(value: Any) -> Any:
    if value is None:
        return value
    if isinstance(value, str) and value.strip():
        return "***redacted***"
    if isinstance(value, list) and value:
        return ["***redacted***"] * len(value)
    return value


def _redact_mapping(mapping: Dict[str, Any], keys: List[str]) -> Dict[str, Any]:
    redacted = dict(mapping)
    for k in keys:
        if k in redacted:
            redacted[k] = _redact_value(redacted[k])
    return redacted


def _safe_env_snapshot() -> Dict[str, Any]:
    keys = [
        # runtime
        "TZ",
        "PORT",
        "ENABLE_WEBSERVER",
        "WEBSERVER_PORT",
        "RUN_MODE",
        "CRON_SCHEDULE",
        "IMMEDIATE_RUN",
        "DOCKER_CONTAINER",
        "GITHUB_ACTIONS",
        "USE_DATA_DIR",
        "DATA_DIR",
        "OUTPUT_DIR",
        "CONFIG_PATH",
        "FREQUENCY_WORDS_PATH",
        # core overrides
        "ENABLE_CRAWLER",
        "ENABLE_NOTIFICATION",
        "REPORT_MODE",
        "SORT_BY_POSITION_FIRST",
        "MAX_NEWS_PER_KEYWORD",
        "REVERSE_CONTENT_ORDER",
        "MIN_TITLE_LENGTH",
        "ALWAYS_INCLUDE_TOP_N",
        "ALWAYS_INCLUDE_GROUP_NAME",
        "ALWAYS_INCLUDE_ONLY_UNMATCHED",
        "PUSH_WINDOW_ENABLED",
        "PUSH_WINDOW_START",
        "PUSH_WINDOW_END",
        "PUSH_WINDOW_ONCE_PER_DAY",
        "MAX_ACCOUNTS_PER_CHANNEL",
        # storage overrides
        "STORAGE_BACKEND",
        "LOCAL_RETENTION_DAYS",
        "REMOTE_RETENTION_DAYS",
        "STORAGE_TXT_ENABLED",
        "STORAGE_HTML_ENABLED",
        "PULL_ENABLED",
        "PULL_DAYS",
        "S3_ENDPOINT_URL",
        "S3_BUCKET_NAME",
        "S3_ACCESS_KEY_ID",
        "S3_SECRET_ACCESS_KEY",
        "S3_REGION",
        # webhooks
        "FEISHU_WEBHOOK_URL",
        "DINGTALK_WEBHOOK_URL",
        "WEWORK_WEBHOOK_URL",
        "WEWORK_MSG_TYPE",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "EMAIL_FROM",
        "EMAIL_PASSWORD",
        "EMAIL_TO",
        "EMAIL_SMTP_SERVER",
        "EMAIL_SMTP_PORT",
        "NTFY_SERVER_URL",
        "NTFY_TOPIC",
        "NTFY_TOKEN",
        "BARK_URL",
        "SLACK_WEBHOOK_URL",
        # admin
        "ADMIN_TOKEN",
    ]

    env = {k: os.environ.get(k) for k in keys if os.environ.get(k) is not None}
    secret_keys = [
        "ADMIN_TOKEN",
        "S3_SECRET_ACCESS_KEY",
        "EMAIL_PASSWORD",
        "TELEGRAM_BOT_TOKEN",
        "NTFY_TOKEN",
        "S3_ACCESS_KEY_ID",
        "FEISHU_WEBHOOK_URL",
        "DINGTALK_WEBHOOK_URL",
        "WEWORK_WEBHOOK_URL",
        "SLACK_WEBHOOK_URL",
        "BARK_URL",
    ]
    return _redact_mapping(env, secret_keys)


@app.get("/api/admin/env")
def admin_get_env(request: Request) -> Any:
    _require_admin(request)
    return JSONResponse({"ok": True, "env": _safe_env_snapshot()})


@app.get("/api/admin/effective-config")
def admin_effective_config(request: Request) -> Any:
    _require_admin(request)
    try:
        from trendradar.core import load_config  # import lazily

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            effective = load_config()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load effective config: {e}")

    secret_keys = [
        "FEISHU_WEBHOOK_URL",
        "DINGTALK_WEBHOOK_URL",
        "WEWORK_WEBHOOK_URL",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "EMAIL_FROM",
        "EMAIL_PASSWORD",
        "EMAIL_TO",
        "NTFY_SERVER_URL",
        "NTFY_TOPIC",
        "NTFY_TOKEN",
        "BARK_URL",
        "SLACK_WEBHOOK_URL",
    ]
    # 只对敏感值进行脱敏
    safe_effective = dict(effective)
    for k in secret_keys:
        if k in safe_effective:
            safe_effective[k] = _redact_value(safe_effective[k])

    return JSONResponse(
        {
            "ok": True,
            "config_path": str(PATHS.config_path),
            "effective": safe_effective,
        }
    )


@app.get("/api/admin/env-snippet")
def admin_env_snippet(request: Request) -> Any:
    _require_admin(request)
    env = _safe_env_snapshot()
    # 提供一个适合 Claw/云平台粘贴的 .env 片段（敏感值保持 ***redacted***）
    preferred_order = [
        "TZ",
        "ENABLE_WEBSERVER",
        "WEBSERVER_PORT",
        "PORT",
        "RUN_MODE",
        "CRON_SCHEDULE",
        "IMMEDIATE_RUN",
        "USE_DATA_DIR",
        "DATA_DIR",
        "OUTPUT_DIR",
        "STORAGE_BACKEND",
        "LOCAL_RETENTION_DAYS",
        "REMOTE_RETENTION_DAYS",
        "STORAGE_TXT_ENABLED",
        "STORAGE_HTML_ENABLED",
        "PULL_ENABLED",
        "PULL_DAYS",
        "S3_ENDPOINT_URL",
        "S3_BUCKET_NAME",
        "S3_ACCESS_KEY_ID",
        "S3_SECRET_ACCESS_KEY",
        "S3_REGION",
        "ENABLE_CRAWLER",
        "ENABLE_NOTIFICATION",
        "REPORT_MODE",
        "ADMIN_TOKEN",
    ]

    lines = []
    for k in preferred_order:
        if k in env:
            v = env[k]
            if v is None:
                continue
            lines.append(f"{k}={v}")

    snippet = "\n".join(lines) + ("\n" if lines else "")
    return JSONResponse({"ok": True, "snippet": snippet})
