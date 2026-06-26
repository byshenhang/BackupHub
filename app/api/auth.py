"""登录认证模块。

密码-only 认证，密码写死在 .env 的 LOGIN_PASSWORD。
使用 Starlette SessionMiddleware 管理会话。
"""

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import settings

router = APIRouter(tags=["auth"])
templates = Jinja2Templates(directory="app/web/templates")


def require_auth(request: Request):
    """登录检查依赖。用于页面路由和 API 路由。"""
    if not request.session.get("logged_in"):
        raise HTTPException(status_code=401, detail="未登录")


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    """登录页面。"""
    error = request.session.pop("login_error", None)
    return templates.TemplateResponse(request, "login.html", {"error": error})


@router.post("/login")
def login_submit(request: Request, password: str = Form(...)):
    """处理登录表单提交。"""
    if not settings.LOGIN_PASSWORD:
        request.session["login_error"] = "服务端未配置登录密码，无法登录。"
        return RedirectResponse("/login", status_code=303)
    if password == settings.LOGIN_PASSWORD:
        request.session["logged_in"] = True
        return RedirectResponse("/", status_code=303)
    else:
        request.session["login_error"] = "密码错误"
        return RedirectResponse("/login", status_code=303)


@router.get("/logout")
def logout(request: Request):
    """登出。"""
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
