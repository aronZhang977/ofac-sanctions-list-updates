# OFAC Sanctions List Updates 监控

监控美国财政部 OFAC [Sanctions List Updates](https://ofac.treasury.gov/recent-actions/sanctions-list-updates)，在名单更新时自动解析新增 / 变更 / 删除记录，导出 Excel，并可按配置发送邮件。

支持范围：个人与实体；变更类型含 add / change / delete。

---

## 功能概览

| 功能 | 说明 |
|------|------|
| 更新检测 | 读取官方 Sanctions List Updates 列表，按状态文件去重 |
| 字段抽取 | 姓名/名称、别名、生日、出生地、国籍、性别、护照、身份证、地址、制裁项目等 |
| 生日格式 | 统一为 `YYYY-MM-DD`；缺月/日时用 `00`，例如 `1959` → `1959-00-00`，`21 Mar 1966` → `1966-03-21` |
| 高亮 | 地址 / 国籍 / 出生地含 China、Hong Kong（含 Hongkong）的行整行高亮 |
| 文件管理 | 同一公告按日期覆盖写入；限制保留数量，避免 `output/` 堆积 |
| 邮件 | SMTP 可配置；未配置时只生成 Excel |
| 跨平台 | macOS / Linux / Windows，本机与公司服务器均可运行 |

---

## 环境要求

- Python **3.9+**
- 能访问 `https://ofac.treasury.gov`（国内网络可能需要在 `config.yaml` 中配置 `ofac.proxy`）

---

## 一键安装

### macOS / Linux

```bash
chmod +x scripts/install.sh
./scripts/install.sh
source .venv/bin/activate
```

### Windows（PowerShell，推荐）

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\install.ps1
.\.venv\Scripts\Activate.ps1
```

### Windows（CMD）

```bat
scripts\install.bat
.venv\Scripts\activate.bat
```

安装脚本会：检测 Python → 创建 `.venv` → 安装依赖 → 初始化 `data/`、`output/`。

### 手动安装（通用）

```bash
python3 -m venv .venv

# macOS / Linux
source .venv/bin/activate

# Windows PowerShell
.\.venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

---

## 快速开始

**推荐先跑配置助手**（对话式，简单选择 / 填写即可）：

```bash
# macOS / Linux
./scripts/setup_config.sh
# 或
python scripts/setup_config.py

# Windows
scripts\setup_config.bat
```

向导覆盖：检查频率、代理、监控范围、Excel、邮件、首次运行策略。密码写入 `.env`（已 gitignore）。配置完成后可直接选择启动（检查一次 / 循环 / 测试公告）。

```bash
# 检查一次（首次只建立基线，不处理历史公告，避免刷屏）
python main.py --once

# 强制处理某条公告（测试用）
python main.py --force-url "https://ofac.treasury.gov/recent-actions/20261009"

# 首次也处理列表里尚未记录的公告
python main.py --process-existing

# 按配置间隔循环检查
python main.py --loop
```

生成的 Excel 默认在 `output/ofac_YYYYMMDD.xlsx`。

---

## 配置说明（`config.yaml`）

### 交互式配置助手（推荐）

```bash
# 全量配置（频率 / 代理 / 范围 / Excel / 邮件 / 首次策略）
./scripts/setup_config.sh          # macOS / Linux
python scripts/setup_config.py
scripts\setup_config.bat           # Windows

# 仅邮件（也可在全量向导里选「仅配置邮件」）
./scripts/setup_email.sh
```

助手支持：新手引导（逐步走完）、分项菜单（只改一块）。有默认值的项会显示 `[默认 xxx，回车确认]`，不输入直接回车即采用默认；选项列表中默认项标 `← 默认`。

### 检查频率

```yaml
schedule:
  interval_minutes: 60   # --loop 时的间隔（分钟）
  timezone: Asia/Shanghai
```

服务器上更推荐用系统定时任务调用 `python main.py --once`，而不是长期 `--loop`。

### Excel 与文件保留

```yaml
excel:
  output_dir: output
  overwrite_by_date: true   # true: ofac_20261009.xlsx 覆盖写入
  max_files: 30             # 最多保留文件数，超出删最旧
  keep_days: 0              # >0 时按天保留；仍受 max_files 限制
  highlight_china_hk:
    enabled: true
    keywords: [china, hong kong, hongkong, hong-kong]
    fill_color: "FFF2CC"    # 高亮底色（Excel 十六进制，不带 #）
  columns:                  # 可增删、调顺序
    - change_type
    - name
    - dob
    - address
    # ...
```

### 邮件（可选）

**推荐：用全量配置助手，或单独跑邮件向导**

```bash
./scripts/setup_config.sh          # 全量（含邮件）
# 仅邮件：
./scripts/setup_email.sh           # macOS / Linux
python scripts/setup_email.py
scripts\setup_email.bat            # Windows
```

向导会询问：是否启用、邮箱类型、SMTP 主机/端口、TLS、用户名、发件人、收件人、环境变量名、密码/授权码，并可选测试 SMTP 登录。

- 非密钥项写入 `config.yaml` 的 `email` 段  
- 密码写入项目根目录 `.env`（已 gitignore，程序启动时自动加载）  
- **不要把 `.env` 提交到仓库**

也可手工配置：

```yaml
email:
  enabled: false            # 改为 true 后启用
  smtp_host: smtp.example.com
  smtp_port: 587
  use_tls: true
  username: sender@example.com
  password_env: SMTP_PASSWORD   # 从环境变量 / .env 读密码，勿写入 yaml
  from_addr: sender@example.com
  to:
    - a@company.com
    - b@company.com
```

手工设置密码示例：

```bash
# 写入 .env（推荐）
echo 'SMTP_PASSWORD=你的密码' >> .env

# 或当前终端临时导出
# macOS / Linux
export SMTP_PASSWORD='你的密码'
# Windows PowerShell
$env:SMTP_PASSWORD = "你的密码"
```

### 范围与代理

```yaml
scope:
  entity_types: [individual, entity, vessel, aircraft, unknown]
  change_types: [add, change, delete]

ofac:
  proxy: null               # 例如 http://127.0.0.1:7890
```

### 首次运行策略

```yaml
runtime:
  mode: once
  process_existing_on_first_run: false   # false=首次只记基线
  max_notices_per_run: 0                 # 调试时可限制条数
```

状态保存在 `data/state.json`，迁机时请一并拷贝，避免重复处理。

---

## 命令行参数

| 参数 | 说明 |
|------|------|
| `-c` / `--config` | 指定配置文件，默认 `./config.yaml` |
| `--once` | 只跑一轮（默认） |
| `--loop` | 按 `schedule.interval_minutes` 循环 |
| `--force-url URL` | 强制解析指定公告并导出 |
| `--process-existing` | 首次也处理未记录公告 |
| `-v` / `--verbose` | 调试日志 |

---

## 定时任务示例

### Linux（cron）

```cron
# 每小时整点执行
0 * * * * cd /path/to/cq && /path/to/cq/.venv/bin/python main.py --once >> /path/to/cq/data/cron.log 2>&1
```

### macOS（cron 或 launchd）

与 Linux cron 相同；也可用「系统设置 → 通用」外的第三方调度，或 `launchd` plist。

### Windows（任务计划程序）

1. 打开「任务计划程序」→ 创建基本任务  
2. 触发器：每小时 / 每天等  
3. 操作：启动程序  

```
程序: C:\path\to\cq\.venv\Scripts\python.exe
参数: main.py --once
起始于: C:\path\to\cq
```

如需邮件，在任务中配置环境变量 `SMTP_PASSWORD`，或在启动前用包装脚本设置。

---

## 输出与高亮说明

- **生日**：`21 Mar 1966` → `1966-03-21`；仅年份 `1959` → `1959-00-00`；`Mar 1966` → `1966-03-00`
- **高亮行**：`address` / `nationality` / `pob` 任一字段匹配 China / Hong Kong 等关键词时，整行填充为配置色（默认浅黄）
- **文件名**：`overwrite_by_date: true` 时为 `output/ofac_20261009.xlsx`；同一天公告再次处理会覆盖，不会无限堆积

---

## 目录结构

```
cq/
├── main.py                 # 入口
├── config.yaml             # 配置
├── requirements.txt
├── README.md
├── scripts/
│   ├── install.sh          # macOS / Linux 安装
│   ├── install.ps1         # Windows PowerShell 安装
│   ├── install.bat         # Windows CMD 安装
│   ├── setup_config.py     # 全量对话式配置助手
│   └── setup_email.py      # 仅邮件配置向导
├── ofac_monitor/           # 业务代码
├── data/state.json         # 已处理公告状态
└── output/                 # Excel 输出
```

---

## 常见问题

**Q: 首次运行没有 Excel？**  
A: 默认 `process_existing_on_first_run: false`，首次只记录当前列表。用 `--force-url` 测一条，或 `--process-existing` 处理未记录公告。

**Q: 访问 OFAC 很慢或失败？**  
A: 运行 `./scripts/setup_config.sh` 配置代理，或在 `config.yaml` 的 `ofac.proxy` 填写 HTTP 代理。

**Q: 邮件没发出？**  
A: 用配置助手启用邮件并写入密码；确认 `email.enabled: true` 且 `.env` / 环境变量中有 `SMTP_PASSWORD`。未就绪时日志会写明跳过原因，Excel 仍会生成。

**Q: 如何迁到公司服务器？**  
A: 拷贝整个项目（含 `config.yaml`、`data/state.json`），在服务器执行安装脚本与 `setup_config`，再用 cron / 计划任务跑 `python main.py --once`。

---

## 免责声明

本工具用于合规筛查辅助，解析结果以 OFAC 官方原文与数据文件为准；请结合贵司合规流程使用。
