@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
rem 切到本文件所在目录，不依赖任何硬编码路径
cd /d "%~dp0"

echo ============================================================
echo   BuddyKeeper - 绑定自定义域名并启用 HTTPS
echo ============================================================
echo.
echo 前提：域名已通过 ICP 备案，且 DNS 的 A 记录已指向服务器。
echo 未满足时脚本会在第一步就停下，不会改动服务器任何东西。
echo.

set /p DOMAIN=请输入已备案的域名（例如 buddy.example.com）：
if "%DOMAIN%"=="" goto abort

echo.
echo [步骤一] 校验 DNS 解析 ...
echo.
python scripts\bind_domain.py --check --domain %DOMAIN%
if errorlevel 1 (
    echo.
    echo DNS 未就绪，已终止。请等解析生效后再双击本文件。
    goto end
)

echo.
set /p EMAIL=请输入证书到期通知邮箱：
if "%EMAIL%"=="" goto abort

echo.
choice /c YN /m "确认开始改动服务器（会自动回滚失败步骤）"
if errorlevel 2 goto abort

echo.
python scripts\bind_domain.py --domain %DOMAIN% --email %EMAIL%

echo.
if errorlevel 1 (
    echo 执行失败，已自动回滚。看板应仍可通过原方式访问。
) else (
    echo 执行成功。请用浏览器打开 https://%DOMAIN%/ 验收。
)
goto end

:abort
echo.
echo 已取消，未改动任何东西。

:end
echo.
pause
