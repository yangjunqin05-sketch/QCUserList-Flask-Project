@echo off
chcp 65001 > nul 2>&1
REM 使用 UTF-8 编码，提高兼容性

REM ===================================================
echo.
echo  QC User List Agent 部署脚本
echo.
echo ===================================================

REM 核心修正：使用 %~dp0 来获取脚本自身所在的完整路径
set "AGENT_EXE_PATH=%~dp0agent.exe"

REM 检查 agent.exe 是否存在
if not exist "%AGENT_EXE_PATH%" (
    echo.
    echo [-] 错误：在脚本所在目录下找不到 agent.exe！
    echo     请确保 agent.exe 和 install.bat 在同一个文件夹中。
    echo.
    pause
    exit /b
)

REM 步骤 1: 运行 agent.exe 的首次设置
echo.
echo [+] 正在启动首次运行设置向导...
echo.
start "" "%AGENT_EXE_PATH%"

REM 等待用户完成设置。这里我们等待一个名为 agent_config.json 的文件被创建
echo.
echo [+] 请在弹出的窗口中完成设置...
:waitloop
timeout /t 2 /nobreak > nul
if exist "%~dp0agent_config.json" (
    goto setup_done
)
if not exist "%AGENT_EXE_PATH%" (
    REM 这是一个用户取消的信号，因为设置程序可能会退出
    goto :waitloop
)
goto :waitloop

:setup_done
echo.
echo [v] 检测到设置已完成。

REM 步骤 2: 将 Agent 添加到 Windows 计划任务
echo.
echo [+] 正在创建开机自启动计划任务...
set "TASK_NAME=QCUserListAgent"

schtasks /delete /tn %TASK_NAME% /f > nul 2>&1
schtasks /create /tn %TASK_NAME% /tr "\"%AGENT_EXE_PATH%\"" /sc ONLOGON /ru System /f

IF %ERRORLEVEL% EQU 0 (
    echo.
    echo [v] 计划任务 "%TASK_NAME%" 创建成功！
    echo     Agent 将在下次系统登录后自动在后台运行。
) ELSE (
    echo.
    echo [-] 错误：无法创建计划任务。请以管理员身份运行此脚本。
)

echo.
echo ===================================================
echo.
echo  部署完成！
echo.
echo ===================================================
pause