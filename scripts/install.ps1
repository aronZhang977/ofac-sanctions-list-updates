# OFAC Monitor 环境安装脚本（Windows PowerShell）
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root
Write-Host "==> 项目目录: $Root"

function Find-Python {
    foreach ($name in @("python", "py")) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) { return $name }
    }
    return $null
}

$Py = Find-Python
if (-not $Py) {
    Write-Host "错误: 未找到 Python。请安装 Python 3.9+："
    Write-Host "  https://www.python.org/downloads/windows/"
    Write-Host "  安装时勾选 Add python.exe to PATH"
    exit 1
}

if ($Py -eq "py") {
    $PyArgs = @("-3")
} else {
    $PyArgs = @()
}

$Ver = & $Py @PyArgs -c "import sys; print('%d.%d' % sys.version_info[:2])"
Write-Host "==> 使用解释器: $Py ($Ver)"
& $Py @PyArgs -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)"
if ($LASTEXITCODE -ne 0) {
    Write-Host "错误: 需要 Python 3.9+，当前为 $Ver"
    exit 1
}

if (-not (Test-Path ".venv")) {
    Write-Host "==> 创建虚拟环境 .venv"
    & $Py @PyArgs -m venv .venv
} else {
    Write-Host "==> 复用已有虚拟环境 .venv"
}

$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -r requirements.txt

New-Item -ItemType Directory -Force -Path "output", "data" | Out-Null
$StateFile = "data\state.json"
if (-not (Test-Path $StateFile)) {
    @'
{
  "processed_urls": [],
  "first_run_done": false
}
'@ | Set-Content -Path $StateFile -Encoding UTF8
}

Write-Host ""
Write-Host "安装完成。"
Write-Host "激活环境:"
Write-Host "  .\.venv\Scripts\Activate.ps1"
Write-Host "试跑一次:"
Write-Host "  python main.py --once"
Write-Host "测试指定公告:"
Write-Host "  python main.py --force-url https://ofac.treasury.gov/recent-actions/20261009"
Write-Host "详细说明见 README.md"