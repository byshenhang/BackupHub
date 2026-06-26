@echo off
REM Backup-Hub Windows 服务安装脚本（使用 NSSM）
REM 需要先下载 NSSM：https://nssm.cc/download
REM 将 nssm.exe 放到 PATH 中或本目录下

set SERVICE_NAME=BackupHub
set PYTHON_PATH=%~dp0venv\Scripts\python.exe
set APP_DIR=%~dp0
set LOG_DIR=%~dp0logs

REM 创建日志目录
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

REM 检查 NSSM
where nssm >nul 2>&1
if %errorlevel% neq 0 (
    echo 错误：未找到 nssm.exe，请先下载 NSSM 并添加到 PATH。
    echo 下载地址：https://nssm.cc/download
    pause
    exit /b 1
)

REM 安装服务
echo 正在安装 %SERVICE_NAME% 服务...
nssm install %SERVICE_NAME% "%PYTHON_PATH%" "-m" "app.main"
nssm set %SERVICE_NAME% AppDirectory "%APP_DIR%"
nssm set %SERVICE_NAME% DisplayName "Backup-Hub Backup Management"
nssm set %SERVICE_NAME% Description "通用备份管理与调度平台"
nssm set %SERVICE_NAME% Start SERVICE_AUTO_START

REM 配置日志
nssm set %SERVICE_NAME% AppStdout "%LOG_DIR%\service-stdout.log"
nssm set %SERVICE_NAME% AppStderr "%LOG_DIR%\service-stderr.log"
nssm set %SERVICE_NAME% AppRotateFiles 1
nssm set %SERVICE_NAME% AppRotateBytes 10485760

REM 配置崩溃重启
nssm set %SERVICE_NAME% AppExit Default Restart
nssm set %SERVICE_NAME% AppRestartDelay 5000

echo.
echo 服务安装完成！
echo 启动服务：nssm start %SERVICE_NAME%
echo 停止服务：nssm stop %SERVICE_NAME%
echo 卸载服务：nssm remove %SERVICE_NAME% confirm
echo.
pause
