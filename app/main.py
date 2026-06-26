"""Backup-Hub 程序入口。

启动 FastAPI 应用、初始化数据库、启动调度器。
运行方式：python -m app.main
"""

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings


# --- 日志配置 ---

def setup_logging():
    """配置日志：同时输出到控制器和文件。"""
    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    # 根日志器
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # 控制台输出
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(log_format))
    root_logger.addHandler(console_handler)

    # 文件输出（带轮转）
    from logging.handlers import RotatingFileHandler
    log_file = settings.LOGS_DIR / "backup-hub.log"
    file_handler = RotatingFileHandler(
        log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(logging.Formatter(log_format))
    root_logger.addHandler(file_handler)


setup_logging()
logger = logging.getLogger("backup-hub")


# --- 应用生命周期 ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动与关闭时执行的操作。"""
    # 启动时
    logger.info("Backup-Hub 正在启动...")

    # 初始化数据库
    from app.db.session import Base, engine
    Base.metadata.create_all(bind=engine)
    logger.info("数据库初始化完成。")

    # 启动调度器并加载任务
    from app.core.scheduler import start_scheduler, load_jobs_from_db
    start_scheduler()
    load_jobs_from_db()

    logger.info(f"Backup-Hub 已启动，监听 {settings.HOST}:{settings.PORT}")

    yield

    # 关闭时
    logger.info("Backup-Hub 正在关闭...")
    from app.core.scheduler import shutdown_scheduler
    shutdown_scheduler()
    logger.info("Backup-Hub 已关闭。")


# --- FastAPI 应用 ---

app = FastAPI(
    title="Backup-Hub",
    description="通用备份管理与调度平台",
    version="0.1.0",
    lifespan=lifespan,
)

# Session 中间件（登录认证用）
session_secret = settings.SESSION_SECRET or "backup-hub-dev-session-key-change-in-production"
app.add_middleware(SessionMiddleware, secret_key=session_secret)

# 挂载静态资源
static_dir = Path(__file__).parent / "web" / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# 401 异常处理：页面请求重定向到登录页，API 请求返回 JSON
@app.exception_handler(401)
async def auth_exception_handler(request: Request, exc: HTTPException):
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": "未登录"}, status_code=401)
    return RedirectResponse("/login", status_code=303)


# 注册路由
from app.api.auth import router as auth_router
from app.api.jobs import router as jobs_router
from app.api.runs import router as runs_router
from app.api.storages import router as storages_router
from app.api.pages import router as pages_router

app.include_router(auth_router)  # 登录/登出接口，无需认证
app.include_router(jobs_router)
app.include_router(runs_router)
app.include_router(storages_router)
app.include_router(pages_router)


# --- 健康检查 ---

@app.get("/api/health")
def health_check():
    """健康检查端点。"""
    return {"status": "ok", "version": "0.1.0"}


# --- 启动入口 ---

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
