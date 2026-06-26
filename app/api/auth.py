"""登录认证模块。

密码-only 认证，密码写死在 .env 的 LOGIN_PASSWORD。
使用 Starlette SessionMiddleware 管理会话。
"""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import settings

router = APIRouter(tags=["auth"])
templates = Jinja2Templates(directory="app/web/templates")


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    """登录页面。"""
    error = request.session.pop("login_error", None)
    return templates.TemplateResponse(request, "login.html", {"error": error})


@router.post("/login")
def login_submit(request: Request, password: str = Form(...)):
    """处理登录表单提交。"""
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


def require_auth(request: Request):
    """登录检查依赖。

    用于页面路由和 API 路由，未登录时：
    - 页面请求：重定向到 /login
    - API 请求：返回 401
    """
    if not request.session.get("logged_in"):
        # 判断是 API 请求还是页面请求
        path = request.url.path
        if path.startswith("/api/"):
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": "未登录"}, status_code=401)
        return RedirectResponse("/login", status_code=303)
    return None
