#!/usr/bin/env python3
"""Configure see without writing credentials into the skill or shell profile."""

import argparse
import getpass
import os
import re
import shlex
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path
import secure_credentials
import usage_log

SEE_AGENTS_START = "<!-- see-skill:start -->"
SEE_AGENTS_END = "<!-- see-skill:end -->"
SEE_AGENTS_RULE = """<!-- see-skill:start -->
用户需要媒体分析且当前原生视觉不足时，可使用 `$see`。先复用已有可读输入；外部发送须符合用户授权。无可用视觉或 OCR 时如实说明限制，不把 OCR 当作完整视觉理解。普通文本、任意 URL 和原生视觉已能完成的任务不触发。
<!-- see-skill:end -->"""
SEE_AGENTS_PATTERN = re.compile(
    re.escape(SEE_AGENTS_START) + r".*?" + re.escape(SEE_AGENTS_END),
    re.DOTALL,
)

from parse_media import (
    DEFAULT_PROVIDER_ORDER,
    PROVIDER_SPECS,
    Provider,
    call_provider,
    config_file_path,
    local_ocr,
    local_setup_hint,
    read_env_file,
    safe_error,
    setting,
)


def fail(message: str) -> None:
    print(f"[ERROR] {message}", file=sys.stderr)
    raise SystemExit(1)


def user_agents_path() -> Path:
    return Path.home() / ".codex" / "AGENTS.md"


def agents_rule_installed(text: str) -> bool:
    return bool(SEE_AGENTS_PATTERN.search(text))


def upsert_agents_rule(text: str) -> str:
    rule = SEE_AGENTS_RULE.strip()
    if SEE_AGENTS_PATTERN.search(text):
        return SEE_AGENTS_PATTERN.sub(rule, text)
    stripped = text.rstrip()
    if not stripped:
        return rule + "\n"
    return stripped + "\n\n" + rule + "\n"


def write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)


def install_agents_rule(path: Path | None = None) -> tuple[Path, bool]:
    path = path or user_agents_path()
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    updated = upsert_agents_rule(existing)
    changed = updated != existing
    if changed:
        write_text_atomic(path, updated)
        usage_log.append("agents_rule_installed", path=str(path))
    return path, changed


def codex_home() -> Path:
    return Path(os.getenv("CODEX_HOME", "") or Path.home() / ".codex").expanduser()


def skill_dest_dir() -> Path:
    return codex_home() / "skills" / "see"


def bundled_skill_dir() -> Path:
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        candidate = Path(meipass) / "see"
        if (candidate / "SKILL.md").is_file():
            return candidate
    return Path(__file__).resolve().parent.parent


def bundled_version() -> str:
    value = os.getenv("SEE_GUI_VERSION", "").strip()
    if value:
        return value
    marker = bundled_skill_dir() / ".see-gui-version"
    if marker.is_file():
        return marker.read_text(encoding="utf-8").strip() or "dev"
    return "dev"


def skill_install_status() -> dict[str, object]:
    dest = skill_dest_dir()
    installed = (dest / "SKILL.md").is_file()
    version = ""
    if installed:
        marker = dest / ".see-gui-version"
        version = (
            marker.read_text(encoding="utf-8").strip()
            if marker.is_file()
            else "unknown"
        )
    return {
        "installed": installed,
        "path": str(dest),
        "version": version,
        "up_to_date": installed and version == bundled_version(),
    }


def install_skill() -> Path:
    source = bundled_skill_dir()
    if not (source / "SKILL.md").is_file():
        raise RuntimeError(f"未找到可安装的 See Skill 资源：{source}")
    dest = skill_dest_dir()
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        source,
        dest,
        ignore=shutil.ignore_patterns("__pycache__", ".git", "node_modules"),
    )
    (dest / ".see-gui-version").write_text(bundled_version(), encoding="utf-8")
    for script in dest.glob("scripts/*.sh"):
        script.chmod(0o755)
    usage_log.append(
        "skill_installed",
        path=str(dest),
        version=bundled_version(),
    )
    return dest


def uninstall_skill() -> bool:
    dest = skill_dest_dir()
    if dest.exists():
        shutil.rmtree(dest)
        usage_log.append("skill_uninstalled", path=str(dest))
        return True
    return False


def cli_bin_dir() -> Path:
    if os.name == "nt":
        return Path(os.getenv("APPDATA", str(Path.home() / "AppData" / "Roaming"))) / "see" / "bin"
    return Path(os.getenv("XDG_BIN_HOME", str(Path.home() / ".local" / "bin"))).expanduser()


def cli_launcher_path() -> Path:
    return cli_bin_dir() / ("see.cmd" if os.name == "nt" else "see")


def _shell_rc_paths() -> list[Path]:
    home = Path.home()
    return [home / ".zshrc", home / ".bashrc", home / ".profile"]


def _rc_export_line() -> str:
    return f'export PATH="{cli_bin_dir()}:$PATH"'


def _cli_on_shell_rc() -> bool:
    line = _rc_export_line()
    return any(
        path.is_file() and line in path.read_text(encoding="utf-8", errors="ignore")
        for path in _shell_rc_paths()
    )


def _cli_on_windows_path() -> bool:
    if os.name != "nt":
        return False
    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "[Environment]::GetEnvironmentVariable('Path','User')",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return False
    directory = str(cli_bin_dir()).lower()
    return directory in result.stdout.lower()


def cli_install_status() -> dict[str, object]:
    launcher = cli_launcher_path()
    installed = launcher.is_file()
    on_path = (
        str(cli_bin_dir()) in os.environ.get("PATH", "").split(os.pathsep)
        or _cli_on_shell_rc()
        or _cli_on_windows_path()
    )
    return {
        "installed": installed,
        "path": str(launcher),
        "on_path": on_path,
    }


def _write_cli_launcher() -> Path:
    launcher = cli_launcher_path()
    launcher.parent.mkdir(parents=True, exist_ok=True)
    skill = skill_dest_dir()
    if not (skill / "SKILL.md").is_file():
        raise RuntimeError("请先安装 See Skill，再安装全局 CLI")
    script = str(skill / "scripts" / "parse_media.py")
    if os.name == "nt":
        content = "\r\n".join([
            "@echo off",
            f'set "SEE_SCRIPT={script}"',
            "where python3 >nul 2>nul",
            "if %errorlevel%==0 (",
            '  python3 "%SEE_SCRIPT%" %*',
            "  exit /b %errorlevel%",
            ")",
            "where python >nul 2>nul",
            "if %errorlevel%==0 (",
            '  python "%SEE_SCRIPT%" %*',
            "  exit /b %errorlevel%",
            ")",
            "echo see requires Python 3 to be installed and on PATH.",
            "exit /b 1",
            "",
        ])
        launcher.write_text(content, encoding="utf-8", newline="")
    else:
        content = "\n".join([
            "#!/bin/sh",
            f'SCRIPT={shlex.quote(script)}',
            'if command -v python3 >/dev/null 2>&1; then',
            '  exec python3 "$SCRIPT" "$@"',
            'fi',
            'exec python "$SCRIPT" "$@"',
            "",
        ])
        launcher.write_text(content, encoding="utf-8")
        launcher.chmod(0o755)
    return launcher


def ensure_cli_on_path() -> list[str]:
    messages: list[str] = []
    directory = str(cli_bin_dir())
    if os.name == "nt":
        if not _cli_on_windows_path():
            command = (
                f"$user=[Environment]::GetEnvironmentVariable('Path','User');"
                f"if ($user -notlike '*{directory}*') {{ "
                f"[Environment]::SetEnvironmentVariable('Path',"
                f"($user.TrimEnd(';') + ';{directory}'), 'User') }}"
            )
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", command],
                check=True,
                capture_output=True,
                text=True,
            )
            messages.append(f"已将 {directory} 加入用户 PATH")
        return messages

    if directory in os.environ.get("PATH", "").split(os.pathsep) or _cli_on_shell_rc():
        return messages
    line = _rc_export_line()
    for rc in _shell_rc_paths():
        if rc.exists():
            content = rc.read_text(encoding="utf-8", errors="ignore")
            if line not in content:
                rc.write_text(content.rstrip() + "\n\n" + line + "\n", encoding="utf-8")
            messages.append(f"已将 {directory} 加入 PATH（{rc}）")
            return messages
    profile = _shell_rc_paths()[-1]
    profile.write_text(line + "\n", encoding="utf-8")
    messages.append(f"已将 {directory} 加入 PATH（{profile}）")
    return messages


def install_cli() -> tuple[Path, list[str]]:
    launcher = _write_cli_launcher()
    path_messages = ensure_cli_on_path()
    usage_log.append("cli_installed", path=str(launcher))
    return launcher, path_messages


def uninstall_cli() -> bool:
    removed = False
    launcher = cli_launcher_path()
    if launcher.is_file():
        launcher.unlink()
        removed = True
    if os.name == "nt":
        directory = str(cli_bin_dir())
        command = (
            f"$user=[Environment]::GetEnvironmentVariable('Path','User');"
            f"$parts=@($user -split ';');"
            f"$parts=$parts | Where-Object {{ $_ -and $_.TrimEnd('\\') -ne '{directory}' }};"
            f"[Environment]::SetEnvironmentVariable('Path',($parts -join ';'),'User')"
        )
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", command],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError:
            pass
        if removed:
            usage_log.append("cli_uninstalled", path=str(launcher))
        return removed
    line = _rc_export_line()
    for rc in _shell_rc_paths():
        if rc.is_file():
            content = rc.read_text(encoding="utf-8", errors="ignore")
            if line in content:
                rc.write_text(
                    "\n".join(
                        item for item in content.splitlines() if item != line
                    ).rstrip()
                    + "\n",
                    encoding="utf-8",
                )
                removed = True
    if removed:
        usage_log.append("cli_uninstalled", path=str(launcher))
    return removed


def remove_agents_rule(path: Path | None = None) -> tuple[Path, bool]:
    path = path or user_agents_path()
    if not path.is_file():
        return path, False
    existing = path.read_text(encoding="utf-8")
    updated = SEE_AGENTS_PATTERN.sub("", existing)
    if updated == existing:
        return path, False
    lines = [line for line in updated.splitlines() if not line.strip()]
    text_lines = [line for line in updated.splitlines() if line.strip()]
    if not text_lines:
        path.unlink()
        return path, True
    # Collapse blank padding while preserving the user's own text lines.
    collapsed = "\n\n".join(section.strip() for section in re.split(r"\n\s*\n", updated.strip()))
    write_text_atomic(path, collapsed + "\n")
    usage_log.append("agents_rule_removed", path=str(path))
    return path, True


def configured_credential_references(
    values: dict[str, str] | None = None,
) -> list[str]:
    values = values if values is not None else read_env_file(config_file_path())
    refs = [
        values[key].strip()
        for key in sorted(values)
        if key.startswith("SEE_CREDENTIAL_REF_") and values[key].strip()
    ]
    return list(dict.fromkeys(refs))


def remove_credentials(
    values: dict[str, str] | None = None,
) -> tuple[list[str], list[str]]:
    removed: list[str] = []
    errors: list[str] = []
    for reference in configured_credential_references(values):
        try:
            secure_credentials.delete(reference)
            removed.append(reference)
        except Exception as exc:
            errors.append(f"{reference}: {safe_error(exc)}")
    if removed:
        usage_log.append("credentials_removed", refs=removed)
    return removed, errors


def remove_config() -> bool:
    path = config_file_path()
    if path.is_file():
        path.unlink()
        usage_log.append("config_removed", path=str(path))
        return True
    return False


def uninstall_integration(
    *,
    skill: bool,
    cli: bool,
    agents: bool,
    config: bool,
    credentials: bool,
    logs: bool,
    agents_path: Path | None = None,
) -> dict[str, object]:
    summary: dict[str, object] = {}
    if cli:
        summary["cli"] = uninstall_cli()
        summary["cli_path"] = str(cli_launcher_path())
    if skill:
        summary["skill"] = uninstall_skill()
    if agents:
        _, summary["agents_rule"] = remove_agents_rule(agents_path)
    if config:
        summary["config"] = remove_config()
    if credentials:
        removed, errors = remove_credentials()
        summary["credentials_removed"] = removed
        summary["credential_errors"] = errors
    if logs:
        summary["logs_cleared"] = usage_log.clear()
    return summary


def print_trigger_hint() -> None:
    print("下一步：复用已有可读图片；也可以提供媒体路径或 URL，例如：")
    print("  使用 see 查看 /path/to/screenshot.png")
    print("原生视觉不足时可显式使用 $see；全局指令适配为可选步骤：")
    print("  python3 scripts/onboard.py --install-agents")
    print("然后重启 Codex。")


def choose_provider() -> str:
    choices = [*PROVIDER_SPECS, "local"]
    print("选择图片 / 视频方案：")
    for index, provider in enumerate(choices, start=1):
        if provider == "local":
            suffix = "（不需要 Key，仅支持图片本地分析）"
        elif not PROVIDER_SPECS[provider].get("requires_key", True):
            suffix = "（不需要 Key，复用本机 CC Switch 代理）"
        elif provider == "custom":
            suffix = "（需要自填 API 地址、Key 和模型）"
        else:
            suffix = ""
        print(f"  {index}. {provider}{suffix}")
    while True:
        answer = input("请输入序号：").strip()
        if answer.isdigit() and 1 <= int(answer) <= len(choices):
            return choices[int(answer) - 1]
        print("请输入有效序号。")


def confirm(prompt: str, default: bool = True) -> bool:
    suffix = " [Y/n] " if default else " [y/N] "
    answer = input(prompt + suffix).strip().lower()
    if not answer:
        return default
    return answer in {"y", "yes", "是"}


def config_status() -> int:
    path = config_file_path()
    values = read_env_file(path)
    print(f"配置文件：{path}")
    print(f"默认方案：{values.get('SEE_PROVIDER', '未设置')}")
    configured = []
    no_key = []
    for provider, spec in PROVIDER_SPECS.items():
        if values.get(f'SEE_CREDENTIAL_REF_{provider.upper()}') or any(os.environ.get(name, '').strip() or values.get(name, '').strip() for name in spec['key_names']):
            configured.append(provider)
        if not spec.get("requires_key", True):
            no_key.append(provider)
    print(f"已配置凭据来源（未验证后端或 API）：{', '.join(configured) if configured else '无'}")
    if no_key:
        print(f"免 Key 适配：{', '.join(no_key)}（复用本机 CC Switch 代理）")
    if setting("CUSTOM_BASE_URL", values):
        print(
            f"自定义模型：{setting('CUSTOM_BASE_URL', values)} / "
            f"{setting('CUSTOM_MODEL', values) or '未设置模型'}"
        )
    print("视频默认：Gemini 3.1 Flash-Lite；平台不可用时 Qwen3.7 Plus")
    agents_path = user_agents_path()
    agents_text = agents_path.read_text(encoding="utf-8") if agents_path.exists() else ""
    print(f"Codex 用户指令：{agents_path}")
    print(f"看图拒绝覆盖：{'已写入' if agents_rule_installed(agents_text) else '未写入（运行 --install-agents）'}")
    try:
        backend = verify_local()
        print(f"本地图片分析：可用（{backend}）")
    except Exception as exc:
        print(f"本地图片分析：不可用（{safe_error(exc)}）")
        print(f"修复方式：{local_setup_hint()}")
    return 0


def png_chunk(kind: bytes, payload: bytes) -> bytes:
    body = kind + payload
    return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)


def test_image(path: Path) -> None:
    width = height = 64
    rows = b"".join(b"\x00" + b"\xff\xff\xff" * width for _ in range(height))
    data = (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + png_chunk(b"IDAT", zlib.compress(rows))
        + png_chunk(b"IEND", b"")
    )
    path.write_bytes(data)


def verify_provider(provider: Provider) -> None:
    with tempfile.TemporaryDirectory(prefix="see-onboard-") as tmp:
        image = Path(tmp) / "check.png"
        test_image(image)
        call_provider(provider, [image], "这是一张测试图片。只回答：配置成功。", retries=1)


def verify_local() -> str:
    with tempfile.TemporaryDirectory(prefix="see-onboard-local-") as tmp:
        image = Path(tmp) / "check.png"
        test_image(image)
        result, _ = local_ocr(image, "auto", "")
        return result["backend"]


def clean_value(value: str, label: str) -> str:
    value = value.strip()
    if "\n" in value or "\r" in value:
        fail(f"{label} 不能包含换行")
    return value


def write_config(values: dict[str, str]) -> Path:
    secret_names = {'SEE_API_KEY'} | {name for spec in PROVIDER_SPECS.values() for name in spec['key_names']}
    if any(values.get(name) for name in secret_names):
        raise RuntimeError('旧配置仍有明文凭据；请明确迁移到系统凭据库后再保存，原文件保持不变')
    path = config_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        os.chmod(path.parent, 0o700)
    lines = [
        "# see 私有配置。不要提交到 Git。",
        *[f"{key}={value}" for key, value in sorted(values.items()) if value],
        "",
    ]
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text("\n".join(lines), encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)
    os.chmod(path, 0o600)
    if os.name == "nt":
        user = getpass.getuser()
        subprocess.run(
            ["icacls", str(path), "/inheritance:r", "/grant:r", f"{user}:F"],
            check=False,
            capture_output=True,
            text=True,
        )
    usage_log.append(
        "config_saved",
        path=str(path),
        provider=values.get("SEE_PROVIDER", ""),
    )
    return path


def update_order(values: dict[str, str], preferred: str) -> None:
    configured = values.get("SEE_PROVIDER_ORDER", "")
    order = [
        item.strip()
        for item in (configured.split(",") if configured else DEFAULT_PROVIDER_ORDER)
        if item.strip() in PROVIDER_SPECS
    ]
    values["SEE_PROVIDER_ORDER"] = ",".join([preferred, *[item for item in order if item != preferred]])


def configure_custom(args: argparse.Namespace, values: dict[str, str]) -> int:
    interactive = args.provider is None

    if args.base_url:
        base_url = clean_value(args.base_url, "供应商地址")
    elif values.get("CUSTOM_BASE_URL"):
        base_url = values["CUSTOM_BASE_URL"]
    else:
        base_url = clean_value(
            input("请输入自定义 API 地址（OpenAI 兼容，例如 https://api.example.com/v1）："),
            "供应商地址",
        )
    if not base_url:
        fail("自定义模型需要 API 地址：使用 --base-url 或 CUSTOM_BASE_URL")

    if args.model:
        image_model = clean_value(args.model, "模型")
    elif values.get("CUSTOM_MODEL"):
        image_model = values["CUSTOM_MODEL"]
    else:
        image_model = clean_value(input("请输入图片模型名："), "模型")
    if not image_model:
        fail("自定义模型需要图片模型名：使用 --model 或 CUSTOM_MODEL")

    video_model = clean_value(values.get("CUSTOM_VIDEO_MODEL", "") or image_model, "视频模型")

    if args.key_stdin:
        api_key = clean_value(sys.stdin.readline(), "API Key")
    else:
        api_key = clean_value(getpass.getpass("请输入自定义 API Key："), "API Key")
    if not api_key:
        fail("API Key 不能为空")

    if not args.skip_check:
        print(f"正在验证 custom / {image_model} ...")
        try:
            verify_provider(Provider("custom", api_key, base_url, image_model))
            print("验证成功。")
        except Exception as exc:
            if not interactive or not confirm(
                f"验证失败：{safe_error(exc)}\n仍然保存配置吗？",
                default=False,
            ):
                fail("配置未保存")

    reference = "see/custom/default"
    secure_credentials.save(reference, api_key)
    for alias in PROVIDER_SPECS["custom"]["key_names"]:
        values.pop(alias, None)
    values["SEE_CREDENTIAL_REF_CUSTOM"] = reference
    values["CUSTOM_BASE_URL"] = base_url
    values["CUSTOM_MODEL"] = image_model
    values["CUSTOM_VIDEO_MODEL"] = video_model

    make_default = not args.no_default
    if interactive:
        make_default = confirm("将 custom 设为默认供应商吗？")
    if make_default:
        values["SEE_PROVIDER"] = "custom"
        update_order(values, "custom")

    path = write_config(values)
    print(f"配置完成：{path}")
    print(
        f"已保存：custom / {image_model}（视频 {video_model}）。"
        "Key 存入系统凭据库，不会写入 Skill。"
    )
    print("右下角仍显示当前主模型是正常的；see 只在需要时调用视觉模型。")
    maybe_install_agents(args, interactive)
    print_trigger_hint()
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="安全配置 see 的图片与视频供应商。")
    parser.add_argument("--provider", choices=[*PROVIDER_SPECS, "local"])
    parser.add_argument("--key-stdin", action="store_true", help="从标准输入读取 Key，不显示在命令行参数中。")
    parser.add_argument("--model", default="", help="可选模型覆盖。")
    parser.add_argument("--base-url", default="", help="可选供应商地址覆盖。")
    parser.add_argument("--no-default", action="store_true", help="保存供应商但不设为默认。")
    parser.add_argument("--skip-check", action="store_true", help="保存前不验证 API。")
    parser.add_argument("--skip-agents", action="store_true", help="不写入 ~/.codex/AGENTS.md 拒绝覆盖规则。")
    parser.add_argument("--install-agents", action="store_true", help="只写入 Codex 用户指令，不改供应商配置。")
    parser.add_argument("--status", action="store_true", help="只显示配置状态，不显示 Key。")
    return parser.parse_args()


def maybe_install_agents(args: argparse.Namespace, interactive: bool) -> None:
    # 全局配置只能由显式 --install-agents 分支写入。
    return


def main() -> int:
    args = parse_args()
    if args.status:
        return config_status()
    if args.install_agents:
        path, changed = install_agents_rule()
        print(f"{'已写入' if changed else '已存在'}看图拒绝覆盖：{path}")
        if changed:
            print("重启 Codex 后生效。")
        print_trigger_hint()
        return 0

    interactive = args.provider is None
    provider_name = args.provider or choose_provider()
    values = read_env_file(config_file_path())

    secret_names = {'SEE_API_KEY'} | {name for spec in PROVIDER_SPECS.values() for name in spec['key_names']}
    if any(values.get(name) for name in secret_names):
        fail('检测到旧明文配置，本次未改动。请先将旧配置移至仅自己可读的备份，重新运行配置入口；验证成功后自行删除旧备份。')

    if provider_name == "local":
        print("正在检查本地图片分析 ...")
        try:
            backend = verify_local()
        except Exception as exc:
            fail(f"本地图片分析不可用：{safe_error(exc)}\n修复方式：{local_setup_hint()}")
        values["SEE_PROVIDER"] = "local"
        path = write_config(values)
        print(f"配置完成：{path}")
        print(f"当前使用本地图片分析（{backend}），不需要 API Key；视频需要云端 Key。")
        print("右下角仍显示当前主模型是正常的；see 不会替换主模型。")
        maybe_install_agents(args, interactive)
        print_trigger_hint()
        return 0

    if provider_name == "custom":
        return configure_custom(args, values)

    spec = PROVIDER_SPECS[provider_name]
    key_name = spec["key_names"][0] if spec["key_names"] else ""
    if key_name:
        if args.key_stdin:
            api_key = clean_value(sys.stdin.readline(), "API Key")
        else:
            api_key = clean_value(getpass.getpass(f"请输入 {provider_name} API Key："), "API Key")
        if not api_key:
            fail("API Key 不能为空")
    else:
        api_key = ""

    model = clean_value(args.model or values.get(spec["model_env"], "") or spec["model"], "模型")
    base_url = clean_value(args.base_url or values.get(spec["base_env"], "") or spec["base_url"], "供应商地址")

    if not args.skip_check:
        print(f"正在验证 {provider_name} / {model} ...")
        try:
            verify_provider(Provider(provider_name, api_key, base_url, model))
            print("验证成功。")
        except Exception as exc:
            if not interactive or not confirm(f"验证失败：{safe_error(exc)}\n仍然保存配置吗？", default=False):
                fail("配置未保存")

    if key_name:
        reference = f'see/{provider_name}/default'
        secure_credentials.save(reference, api_key)
        for alias in spec['key_names']:
            values.pop(alias, None)
        values[f'SEE_CREDENTIAL_REF_{provider_name.upper()}'] = reference
    else:
        print("此适配不需要单独 API Key；模型走本机 CC Switch 代理。")
    if args.model:
        values[spec["model_env"]] = model
    if args.base_url:
        values[spec["base_env"]] = base_url

    make_default = not args.no_default
    if interactive:
        make_default = confirm(f"将 {provider_name} 设为默认供应商吗？")
    if make_default:
        values["SEE_PROVIDER"] = provider_name
        update_order(values, provider_name)

    path = write_config(values)
    print(f"配置完成：{path}")
    if key_name:
        print(f"已保存：{provider_name} / {model}。图片和视频可共用此 Key，Key 不会写入 Skill。")
    else:
        print(f"已保存：{provider_name} / {model}。")
    print("右下角仍显示当前主模型是正常的；see 只在需要时调用视觉模型。")
    maybe_install_agents(args, interactive)
    print_trigger_hint()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
