@echo off
setlocal
REM OFAC Monitor 环境安装脚本（Windows CMD）
cd /d "%~dp0.."
echo ==> 项目目录: %CD%

where python >nul 2>nul
if errorlevel 1 (
  where py >nul 2>nul
  if errorlevel 1 (
    echo 错误: 未找到 Python。请安装 Python 3.9+ 并勾选 Add to PATH
    echo https://www.python.org/downloads/windows/
    exit /b 1
  )
  set PY=py -3
) else (
  set PY=python
)

echo ==> 使用解释器: %PY%
%PY% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)"
if errorlevel 1 (
  echo 错误: 需要 Python 3.9+
  exit /b 1
)

if not exist ".venv" (
  echo ==> 创建虚拟环境 .venv
  %PY% -m venv .venv
) else (
  echo ==> 复用已有虚拟环境 .venv
)

call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

if not exist output mkdir output
if not exist data mkdir data
if not exist data\state.json (
  > data\state.json echo {
  >> data\state.json echo   "processed_urls": [],
  >> data\state.json echo   "first_run_done": false
  >> data\state.json echo }
)

echo.
echo 安装完成。
echo 激活环境: .venv\Scripts\activate.bat
echo 试跑一次: python main.py --once
echo 详细说明见 README.md
endlocal