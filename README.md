<p align="center">
  <img src="./assets/readme/hero.svg" width="100%" alt="see 为任何不支持多模态的模型补充原生图片与视频理解">
</p>

分析图片、截图和视频，输出可阅读的媒体报告，并在适用时使用本地文字识别。SeeGui 桌面端负责完整闭环：全局安装 See Skill 与 `see` CLI、随时卸载、配置供应商和截图选项、查看识图与安装日志。

## 不要拖图

如果当前宿主在 Skill 启动前拒绝图片附件，可以提供可读的本地路径；不能据此断言所有宿主都会拒绝附件。

把图片保存到本地，发送路径或 URL，或显式输入 `$see`：

```text
使用 see 查看 /Users/me/Desktop/error.png
```

```text
$see
```

配置凭据不会修改全局规则。Skill 安装后只在本机生效；只有用户明确要求时才会写入 `~/.codex/AGENTS.md` 的看图拒绝覆盖规则，它是可选宿主适配，不是图片分析的前置步骤。

## 安装 SeeGui（推荐）

从 GitHub Releases 下载当前平台的安装包：

| 平台 | 安装包 |
|---|---|
| Windows | `SeeGui-1.0.20260919-windows-x64-setup.exe` |
| macOS | `SeeGui-1.0.20260919-macos-<arch>.dmg` |
| Linux | `SeeGui-1.0.20260919-linux-x86_64.AppImage` |

推送 `v*` tag 时，GitHub Actions 会自动构建三平台安装包并创建/更新 Release；用同一版本号重新打 tag 会覆盖旧包。

启动 SeeGui 后按三个页签完成闭环：

1. **配置**：选择供应商（ZenMux、百炼、OpenRouter、TokenDance、LongCat、自定义、本地），填写 API 地址、Key、模型后“验证并保存”；下方“截图与本地选项”可设置输出目录、OCR 后端、OCR 语言和并行任务数。
2. **安装 / 状态**：点击“安装 / 更新全局组件”，把 See Skill 安装到 `~/.codex/skills/see`，把全局 CLI 安装到 `~/.local/bin/see`（Windows 为 `%APPDATA%\see\bin\see.cmd`）并加入 PATH。以后可以在任何目录直接使用 `see` 命令。卸载时勾选 Skill、CLI、AGENTS 规则、配置文件、系统凭据或使用日志，点击“执行选定卸载”即可。
3. **日志**：识图开始、成功、失败以及安装/卸载/配置保存都会记录到 `~/.config/see/usage.log`（Windows 为 `%APPDATA%\see\usage.log`）。日志页显示最近 200 条、成功/失败次数，可刷新或清空；日志不包含 API Key 或媒体原文。

安装 Skill 不会更换右下角的主模型。继续显示原来的文本模型是正常的，`see` 只在查看媒体时调用视觉后端。

没有多模态 Key 也能使用：供应商选择 `local` 即可走系统视觉 / OCR。

## 直接使用

像平常一样告诉 AI 图片在哪里、想看什么：

```text
看看 /path/to/screenshot.png
```

```text
识别 /path/to/error.png 里的报错，并告诉我怎么修
```

```text
并行查看 a.png、b.png、c.png
```

```text
比较 before.png 和 after.png 的界面变化
```

```text
总结 /path/to/demo.mp4 的内容
```

AI 只需要调用一个命令。安装过 SeeGui 的全局 CLI 后，直接使用 `see`：

```bash
# 单图
see screenshot.png

# 多图独立分析，默认并行
see a.png b.png c.png

# 多图联合理解
see --together before.png after.png --task "比较界面变化"

# 完整视频理解
see demo.mp4
```

未安装全局 CLI 时，仓库内路径也等价：`see/scripts/see.sh <参数>`。

## 为什么更接近原生视觉

- 图片原图直接发送，不预先 OCR、缩放或压缩。
- 视频保持完整时间线和音频，直接使用模型原生视频能力，不在 Skill 内抽帧。
- 4K、高帧率或大体积视频自动压缩为清晰的 H.264 MP4，减少上传时间。
- 用户问题通过 `--task` 原样交给视觉模型，不套固定报告模板。
- 视觉模型同时理解对象、布局、空间关系、界面状态和文字。
- 云端结果直接返回给主模型，减少“先泛化描述、再二次推理”的信息损失。

纯文本主模型最终仍然接收文字结果，因此不可能和同一个模型原生拥有视觉完全相同；但这是外接视觉模型时信息损失最少的方式。

## 并行与联合

| 场景 | 模式 | 行为 |
|---|---|---|
| 多张图片互不相关 | 默认 | 并行请求，结果按输入顺序汇总 |
| 前后对比、连续截图、组合证据 | `--together` | 所有原图进入同一次多模态请求 |
| 只有本地能力可用 | 自动降级 | 多张图片继续并行分析 |

## 供应商

| 供应商 | 默认模型 | Key 变量 |
|---|---|---|
| ZenMux | `qwen/qwen3.7-plus` | `ZENMUX_API_KEY` |
| 百炼 | `qwen3.7-plus` | `DASHSCOPE_API_KEY` |
| OpenRouter | `qwen/qwen3.7-plus` | `OPENROUTER_API_KEY` |
| TokenDance | `qwen3.7-plus` | `TOKENDANCE_API_KEY` |
| LongCat / CC Switch | `deepseek-v4-flash-vision-exp` | 本机 CC Switch，无需 Key |
| DeepSeek | `deepseek-v4-flash-vision` | `DEEPSEEK_API_KEY` |
| 自定义（OpenAI 兼容） | 用户填写 | `CUSTOM_BASE_URL` / `CUSTOM_MODEL` / `CUSTOM_API_KEY` |
| 本地 | 系统视觉 / OCR | 不需要 |

图片会按配置顺序尝试供应商，全部失败才进入本地视觉分析；视频使用下方的独立路由。

`longcat` 不是让 LongCat 2.0 主模型直接收图，而是复用 CC Switch 本地代理调用可收图的视觉模型。默认地址是 `http://127.0.0.1:15721/v1`，端口不同时用 `LONGCAT_BASE_URL` 覆盖；模型用 `LONGCAT_MODEL` 覆盖。该适配不在默认自动路由里，使用 `--provider longcat` 或 `SEE_PROVIDER=longcat` 启用。

`custom` 适配任意 OpenAI 兼容的视觉接口。地址、Key 和模型都由用户决定：API 地址用 `CUSTOM_BASE_URL`，图片模型用 `CUSTOM_MODEL`，Key 用 `CUSTOM_API_KEY`；视频模型用 `CUSTOM_VIDEO_MODEL`，缺省复用 `CUSTOM_MODEL`。

```bash
# 方式 A：终端引导，Key 存入系统凭据库
python3 see/scripts/onboard.py --provider custom

# 方式 B：环境变量或项目 .env.local
export CUSTOM_BASE_URL=https://api.example.com/v1
export CUSTOM_MODEL=vision-model
export CUSTOM_API_KEY=sk-...
see/scripts/see.sh image.png --provider custom
```

视频模型自动选择：

| 供应商 | 默认视频模型 | 输入 |
|---|---|---|
| ZenMux | `google/gemini-3.1-flash-lite` | 完整视频 + 音频 |
| OpenRouter | `google/gemini-3.1-flash-lite` | 完整视频 + 音频 |
| 百炼 | `qwen3.7-plus` | 完整视频 |
| TokenDance | `qwen3.7-plus` | 完整视频 |
| 自定义 | 用户填写，缺省复用 `CUSTOM_MODEL` | 完整视频（取决于端点） |

视频不会降级为抽帧；没有支持视频的云端 Key 时会直接提示配置。

## Onboard 与 Key 保存

推荐用 SeeGui 配置供应商并全局安装；新 Key 使用固定页面，云端执行通过对应配置的 run 包装器。旧 Onboard 保留给用户主动选择的终端配置、路由调整和本地模式：

```bash
python3 see/scripts/onboard.py
# 仅明确要求修改全局规则时：python3 see/scripts/onboard.py --install-agents
python3 see/scripts/onboard.py --status
```

私有配置位置：

- macOS / Linux：`~/.config/see/config.env`
- Windows：`%APPDATA%\see\config.env`

普通配置保存供应商、模型和系统凭据引用，并限制为仅当前用户可读写；新密钥不写入该文件。环境变量优先级最高，适合 CI 或不希望落盘的用户；项目 `.env.local` 其次，用户私有配置最后。

高级用户也可以直接设置：

```bash
export SEE_PROVIDER=zenmux
# ZENMUX_API_KEY 由可信运行环境注入，不在命令正文填写
```

不要把真实 Key 提交到 Git。

## SeeGui 生命周期

SeeGui 由 Tkinter 编写，打包为三平台桌面应用。安装包内的 SeeGui 同时携带完整 See Skill 资源，因此可以离线完成全局安装与卸载：

- **安装**：`安装 / 更新全局组件` 会先安装 See Skill 到 `~/.codex/skills/see`，再创建全局 `see` 命令并加入 PATH，可选写入 `~/.codex/AGENTS.md` 的看图拒绝覆盖规则。
- **状态**：页面实时显示 Skill 版本与安装路径、CLI 路径与 PATH 状态、AGENTS 规则是否写入。
- **卸载**：按勾选执行，可分别卸载 Skill、全局 CLI、AGENTS 规则、配置文件、系统凭据和使用日志，无需手动清理。
- **日志**：识图开始 / 成功 / 失败、安装 / 卸载、配置保存都写入 JSONL 日志；页面显示最近 200 条、成功失败统计，可刷新和清空。

直接运行源码版本：

```bash
python3 see/scripts/gui.py
```

API Key 留空时保留系统凭据库中已有的值；Key 始终不写入配置文件和日志。

GitHub Actions 会为每个平台构建桌面安装包，并支持本地手动构建：

| 平台 | 产物 |
|---|---|
| Windows | NSIS 安装包（`SeeGui-<version>-windows-x64-setup.exe`） |
| macOS | DMG（`SeeGui-<version>-macos-<arch>.dmg`） |
| Linux | AppImage（`SeeGui-<version>-linux-x86_64.AppImage`） |

推送 `v*` tag 时 CI 自动构建并发布三个安装包。本机构建使用 `python3 packaging/build_installers.py --installer nsis|dmg|appimage`，详见 [packaging/README.md](packaging/README.md)。

## 本地降级

```text
macOS   → 系统 Vision OCR → Tesseract
Windows → Windows OCR  → Tesseract
Linux   → Tesseract
```

macOS Vision 通过系统自带的 `osascript` 调用，不需要 Xcode、Swift 或额外 Key；如果设备已经有 Swift，会自动启用增强分析。Windows OCR 也是系统能力，但需要安装 OCR 语言。Tesseract 是最后兜底，需要用户自行安装。

macOS 的 Swift 增强路径还会返回场景分类、人物/人脸、条码和基础图形结构；这些线索仍不能替代多模态模型的完整语义理解。其他本地路径目前以 OCR 为主。

检查本地后端：

```bash
python3 see/scripts/onboard.py --status
```

如果显示不可用：

- macOS：升级到 macOS 10.15 或更高版本。
- Windows：设置 → 时间和语言 → 语言和区域 → 语言选项，安装 OCR。
- Ubuntu / Debian：`sudo apt install tesseract-ocr tesseract-ocr-chi-sim`。

## 参数

日常使用只需要图片路径。其余参数按需使用：

| 参数 | 用途 |
|---|---|
| `--task "问题"` | 原样发送给视觉模型 |
| `--together` | 多图放进同一次请求 |
| `--jobs 4` | 多图并发数 |
| `--provider NAME` | 临时指定供应商 |
| `--model NAME` | 临时覆盖当前媒体模型 |
| `--ocr-backend system` | 指定本地系统能力 |
| `-o result.md` | 指定结果文件 |

成功后 stdout 只输出：

```text
output_path=/absolute/path/result.md
```

结果 Markdown 会记录实际后端、模型、单图/并行/联合模式，以及每次路由是否成功，方便 AI 判断有没有发生降级。

## 支持范围

- 支持本地图片、视频和 HTTP / HTTPS URL。
- 支持多文件并行；`--together` 用于多图联合理解。
- 视频自动压缩为最长边 1920、2 fps、H.264 和 AAC；超出上传预算时自动切换紧凑档。
- 下载上限为 512 MB。
- 不负责网页视频提取。
- 需要 Python 3；云端调用不依赖第三方 Python 包。
- 视频压缩需要 FFmpeg。

## 文件结构

```text
see/
├── SKILL.md
├── agents/
│   └── openai.yaml
└── scripts/
    ├── see.sh
    ├── onboard.py
    ├── parse_media.py
    ├── usage_log.py
    ├── gui.py
    ├── ocr_macos.js
    ├── ocr_macos.swift
    └── ocr_windows.ps1
```

## License

[MIT](./LICENSE) © 2026 tyza66

## 凭据与数据边界

云端分析会把选定媒体发给所选供应商，可能计费；本地 OCR 不等于完整视觉理解。新密钥通过随附本机配置页存入系统凭据库，普通配置只保存引用。先用任务 Python 环境安装 `see/scripts/requirements-credentials.txt`（Skill 内相对路径为 `scripts/requirements-credentials.txt`）。不把 Key 发到聊天、命令参数或日志；使用日志只记录事件、供应商、模型、计数和脱敏错误，不记录 Key 或媒体原文。旧明文配置不会自动迁移或覆盖：入口会先停止，提示备份后重新配置。状态检查只确认来源，API 验证成功才代表可用。全局指令写入仅在明确调用 `--install-agents` 或 SeeGui 安装时勾选后发生。

## API Key 配置页面

首次使用外部服务时，可以在本机配置页亲自填写 Key；已有配置会复用，密钥存入系统凭据库。只为实际使用的外部服务配置；纯本地处理不需要 Key。页面需要 Node.js 22.18+ 与可用的系统凭据服务，业务运行仍使用原依赖。

安装、状态检查、打开页面和带凭据运行的完整入口见[配置说明](see/references/api-key-setup.md)。页面保存与业务读取已经接通；不把 Key 发进聊天，也不自动迁移旧文件。
