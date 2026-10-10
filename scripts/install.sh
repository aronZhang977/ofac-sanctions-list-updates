#!/usr/bin/env bash
# OFAC Monitor 环境安装脚本（macOS / Linux）
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "==> 项目目录: $ROOT"

detect_python() {
  if command -v python3 >/dev/null 2>&1; then
    echo "python3"
    return
  fi
  if command -v python >/dev/null 2>&1; then
    echo "python"
    return
  fi
  echo ""
}

PY="$(detect_python)"
if [[ -z "$PY" ]]; then
  echo "错误: 未找到 Python。请先安装 Python 3.9+："
  echo "  macOS : brew install python  或从 https://www.python.org/downloads/ 安装"
  echo "  Ubuntu/Debian: sudo apt update && sudo apt install -y python3 python3-venv python3-pip"
  echo "  CentOS/RHEL  : sudo yum install -y python3 python3-pip"
  exit 1
fi

VER="$($PY -c 'import sys; print("%d.%d"%sys.version_info[:2])')"
echo "==> 使用解释器: $PY ($VER)"
$PY -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)' || {
  echo "错误: 需要 Python 3.9+，当前为 $VER"
  exit 1
}

if [[ ! -d .venv ]]; then
  echo "==> 创建虚拟环境 .venv"
  $PY -m venv .venv
else
  echo "==> 复用已有虚拟环境 .venv"
fi

# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

mkdir -p output data
if [[ ! -f data/state.json ]]; then
  cat > data/state.json <<'EOF'
{
  "processed_urls": [],
  "first_run_done": false
}
EOF
fi

echo ""
echo "安装完成。"
echo "激活环境:"
echo "  source .venv/bin/activate"
echo "试跑一次:"
echo "  python main.py --once"
echo "测试指定公告:"
echo "  python main.py --force-url https://ofac.treasury.gov/recent-actions/20261009"
echo "详细说明见 README.md"