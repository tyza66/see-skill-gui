#!/usr/bin/env python3
"""Tkinter GUI for configuring and installing see."""

from __future__ import annotations

import os
import subprocess
import sys
import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, scrolledtext, ttk
except ImportError:  # Keep save-plan logic testable on headless Python.
    tk = None
    filedialog = messagebox = scrolledtext = ttk = None

import onboard
import parse_media
import secure_credentials
import usage_log


APP_TITLE = "See 配置与安装"
PROVIDER_ORDER = [
    "local",
    "longcat",
    "zenmux",
    "bailian",
    "openrouter",
    "tokendance",
    "custom",
]
PROVIDER_LABELS = {
    "local": "本地视觉 / OCR",
    "longcat": "LongCat / CC Switch（免 Key）",
    "zenmux": "ZenMux",
    "bailian": "百炼",
    "openrouter": "OpenRouter",
    "tokendance": "TokenDance",
    "custom": "自定义 OpenAI 兼容接口",
}
OCR_BACKEND_CHOICES = ("auto", "system", "tesseract")
ADVANCED_KEYS = ("SEE_OUTPUT_DIR", "SEE_OCR_BACKEND", "SEE_OCR_LANGUAGES", "SEE_JOBS")


@dataclass
class SavePlan:
    provider: str
    values: dict[str, str]
    verify: parse_media.Provider | None
    api_key: str
    reference: str
    save_secret: bool


@dataclass
class UninstallPlan:
    skill: bool
    cli: bool
    agents: bool
    config: bool
    credentials: bool
    logs: bool

    def ready(self) -> bool:
        return any((
            self.skill,
            self.cli,
            self.agents,
            self.config,
            self.credentials,
            self.logs,
        ))

    def summary(self) -> str:
        labels = {
            "skill": "See Skill（~/.codex/skills/see）",
            "cli": "全局 CLI（see 命令与 PATH 条目）",
            "agents": "AGENTS.md 看图拒绝覆盖规则",
            "config": "配置文件 config.env",
            "credentials": "系统凭据库中的 See Key",
            "logs": "使用日志",
        }
        return "\n".join(
            f"- {labels[key]}"
            for key in ("skill", "cli", "agents", "config", "credentials", "logs")
            if getattr(self, key)
        )


def advanced_values_from_gui(
    output_dir: str,
    ocr_backend: str,
    ocr_languages: str,
    jobs: str,
) -> dict[str, str]:
    result: dict[str, str] = {}
    if output_dir.strip():
        result["SEE_OUTPUT_DIR"] = output_dir.strip()
    if ocr_backend.strip():
        if ocr_backend not in OCR_BACKEND_CHOICES:
            raise ValueError("OCR 后端需要是 auto / system / tesseract")
        result["SEE_OCR_BACKEND"] = ocr_backend
    if ocr_languages.strip():
        result["SEE_OCR_LANGUAGES"] = ocr_languages.strip()
    if jobs.strip():
        try:
            count = int(jobs.strip())
        except ValueError:
            raise ValueError("并发任务数必须是正整数") from None
        if count <= 0:
            raise ValueError("并发任务数必须是正整数")
        result["SEE_JOBS"] = str(count)
    return result


def display_advanced_values() -> tuple[str, str, str, str]:
    values = current_values()
    return (
        values.get("SEE_OUTPUT_DIR", ""),
        values.get("SEE_OCR_BACKEND", "auto"),
        values.get("SEE_OCR_LANGUAGES", ""),
        values.get("SEE_JOBS", "4"),
    )


def format_log_entry(record: dict[str, object]) -> str:
    fields = []
    for key, value in record.items():
        if key in ("ts", "event"):
            continue
        rendered = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        fields.append(f"{key}={rendered}")
    header = f"{record.get('ts', '')}  {record.get('event', 'unknown')}"
    return header + (("  " + "  ".join(fields)) if fields else "")


def log_summary(entries: list[dict[str, object]]) -> dict[str, object]:
    success = sum(1 for item in entries if item.get("event") == "analyze_success")
    failed = sum(1 for item in entries if item.get("event") == "analyze_failed")
    last_ts = entries[-1].get("ts", "") if entries else ""
    return {"total": len(entries), "success": success, "failed": failed, "last": last_ts}


def current_values() -> dict[str, str]:
    return onboard.read_env_file(onboard.config_file_path())


def build_save_plan(
    provider: str,
    api_key: str,
    base_url: str,
    image_model: str,
    video_model: str,
    make_default: bool,
    values: dict[str, str] | None = None,
) -> SavePlan:
    """Translate GUI fields into the same private config shape as onboard."""

    values = dict(values if values is not None else current_values())
    if provider not in parse_media.PROVIDER_SPECS and provider != "local":
        raise ValueError(f"未知供应商：{provider}")

    if provider == "local":
        if make_default:
            values["SEE_PROVIDER"] = "local"
        return SavePlan("local", values, None, "", "", False)

    spec = parse_media.PROVIDER_SPECS[provider]
    resolved_base = base_url.strip() or spec["base_url"]
    resolved_model = image_model.strip() or spec["model"]
    resolved_video = video_model.strip() or spec["video_model"] or resolved_model

    if provider == "custom":
        if not resolved_base:
            raise ValueError("自定义模型需要 API 地址")
        if not resolved_model:
            raise ValueError("自定义模型需要图片模型名")

    key_name = spec["key_names"][0] if spec["key_names"] else ""
    reference = f"see/{provider}/default"
    existing_ref = values.get(f"SEE_CREDENTIAL_REF_{provider.upper()}", "")
    cleaned_key = api_key.strip()

    if key_name and not cleaned_key and not existing_ref:
        raise ValueError(f"请输入 {provider} API Key")

    for alias in spec["key_names"]:
        values.pop(alias, None)
    if cleaned_key:
        values[f"SEE_CREDENTIAL_REF_{provider.upper()}"] = reference
    elif existing_ref:
        values[f"SEE_CREDENTIAL_REF_{provider.upper()}"] = existing_ref

    values[spec["base_env"]] = resolved_base
    values[spec["model_env"]] = resolved_model
    values[spec["video_model_env"]] = resolved_video
    if make_default:
        values["SEE_PROVIDER"] = provider
        onboard.update_order(values, provider)

    verify = parse_media.Provider(
        provider,
        cleaned_key,
        resolved_base,
        resolved_model,
        requires_key=bool(spec.get("requires_key", True)),
    )
    return SavePlan(provider, values, verify, cleaned_key, reference, bool(cleaned_key))


class SeeGui:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title(APP_TITLE)
        self.root.geometry("760x640")
        self.root.minsize(700, 560)

        self.provider_var = tk.StringVar(value="local")
        self.api_key_var = tk.StringVar()
        self.base_url_var = tk.StringVar()
        self.image_model_var = tk.StringVar()
        self.video_model_var = tk.StringVar()
        self.make_default_var = tk.BooleanVar(value=True)
        self.skip_check_var = tk.BooleanVar(value=False)
        self.install_agents_var = tk.BooleanVar(value=True)
        self.output_dir_var = tk.StringVar()
        self.ocr_backend_var = tk.StringVar(value="auto")
        self.ocr_languages_var = tk.StringVar()
        self.jobs_var = tk.StringVar(value="4")
        self.uninstall_vars = {
            "skill": tk.BooleanVar(value=False),
            "cli": tk.BooleanVar(value=False),
            "agents": tk.BooleanVar(value=False),
            "config": tk.BooleanVar(value=False),
            "credentials": tk.BooleanVar(value=False),
            "logs": tk.BooleanVar(value=False),
        }
        self.auto_refresh_var = tk.BooleanVar(value=True)

        self._build_ui()
        self._load_advanced_values()
        self._refresh_install_status()
        self._refresh_logs()
        self._refresh_for_provider()
        self._set_status(
            f"配置文件：{onboard.config_file_path()}\n"
            "选择供应商并填写配置；API Key 留空表示保留系统凭据库中已有的值。"
        )

    def _build_ui(self) -> None:
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=12, pady=12)

        config_tab = ttk.Frame(notebook, padding=12)
        install_tab = ttk.Frame(notebook, padding=12)
        log_tab = ttk.Frame(notebook, padding=12)
        notebook.add(config_tab, text="配置")
        notebook.add(install_tab, text="安装 / 状态")
        notebook.add(log_tab, text="日志")

        self._build_config_tab(config_tab)
        self._build_install_tab(install_tab)
        self._build_log_tab(log_tab)

    def _build_config_tab(self, parent: ttk.Frame) -> None:
        form = ttk.Frame(parent)
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="供应商").grid(row=0, column=0, sticky="w", pady=4)
        provider_box = ttk.Combobox(
            form,
            textvariable=self.provider_var,
            values=PROVIDER_ORDER,
            state="readonly",
        )
        provider_box.grid(row=0, column=1, sticky="ew", pady=4)
        provider_box.bind("<<ComboboxSelected>>", lambda _event: self._refresh_for_provider())

        labels = {
            "api_key": "API Key",
            "base_url": "API 地址",
            "image_model": "图片模型",
            "video_model": "视频模型",
        }
        self.field_labels: dict[str, ttk.Label] = {}
        self.field_entries: dict[str, ttk.Entry] = {}

        for index, key in enumerate(("api_key", "base_url", "image_model", "video_model"), start=1):
            label = ttk.Label(form, text=labels[key])
            label.grid(row=index, column=0, sticky="w", pady=4)
            self.field_labels[key] = label

            show = "*" if key == "api_key" else ""
            entry = ttk.Entry(form, show=show)
            entry.grid(row=index, column=1, sticky="ew", pady=4)
            self.field_entries[key] = entry

        self.api_key_var.trace_add("write", lambda *_: self._mark_api_key_optional())
        self.base_url_var.set("")
        self.image_model_var.set("")
        self.video_model_var.set("")
        self.field_entries["api_key"].config(textvariable=self.api_key_var)
        self.field_entries["base_url"].config(textvariable=self.base_url_var)
        self.field_entries["image_model"].config(textvariable=self.image_model_var)
        self.field_entries["video_model"].config(textvariable=self.video_model_var)

        options = ttk.Frame(parent)
        options.pack(fill="x", pady=8)
        ttk.Checkbutton(
            options,
            text="设为默认供应商",
            variable=self.make_default_var,
        ).pack(side="left")
        ttk.Checkbutton(
            options,
            text="跳过 API 验证",
            variable=self.skip_check_var,
        ).pack(side="left", padx=16)

        actions = ttk.Frame(parent)
        actions.pack(fill="x", pady=6)
        ttk.Button(actions, text="验证并保存", command=self._save_from_gui).pack(side="left")
        ttk.Button(actions, text="仅测试当前配置", command=self._test_from_gui).pack(side="left", padx=8)

        advanced = ttk.LabelFrame(parent, text="截图与本地选项", padding=8)
        advanced.pack(fill="x", pady=(6, 0))
        advanced.columnconfigure(1, weight=1)
        advanced.columnconfigure(3, weight=1)
        ttk.Label(advanced, text="输出目录").grid(row=0, column=0, sticky="w", pady=3)
        ttk.Entry(advanced, textvariable=self.output_dir_var).grid(
            row=0,
            column=1,
            sticky="ew",
            pady=3,
        )
        ttk.Label(advanced, text="OCR 后端").grid(
            row=0,
            column=2,
            sticky="w",
            pady=3,
            padx=(10, 0),
        )
        ttk.Combobox(
            advanced,
            textvariable=self.ocr_backend_var,
            values=OCR_BACKEND_CHOICES,
            state="readonly",
            width=10,
        ).grid(row=0, column=3, sticky="ew", pady=3)
        ttk.Label(advanced, text="OCR 语言").grid(row=1, column=0, sticky="w", pady=3)
        ttk.Entry(advanced, textvariable=self.ocr_languages_var).grid(
            row=1,
            column=1,
            sticky="ew",
            pady=3,
        )
        ttk.Label(advanced, text="并行任务数").grid(
            row=1,
            column=2,
            sticky="w",
            pady=3,
            padx=(10, 0),
        )
        ttk.Entry(advanced, textvariable=self.jobs_var, width=10).grid(
            row=1,
            column=3,
            sticky="ew",
            pady=3,
        )
        advanced_actions = ttk.Frame(advanced)
        advanced_actions.grid(row=2, column=0, columnspan=4, sticky="w", pady=(8, 0))
        ttk.Button(
            advanced_actions,
            text="保存截图与本地选项",
            command=self._save_advanced_from_gui,
        ).pack(side="left")
        ttk.Button(
            advanced_actions,
            text="载入当前值",
            command=self._load_advanced_values,
        ).pack(side="left", padx=8)

        self.status = scrolledtext.ScrolledText(parent, height=9, state="disabled", wrap="word")
        self.status.pack(fill="both", expand=True, pady=8)

    def _build_install_tab(self, parent: ttk.Frame) -> None:
        ttk.Label(
            parent,
            text="全局安装、状态与卸载",
            font=("", 13, "bold"),
        ).pack(anchor="w", pady=(0, 10))

        status_grid = ttk.Frame(parent)
        status_grid.pack(fill="x")
        status_grid.columnconfigure(1, weight=1)
        self.skill_status_var = tk.StringVar(value="未检测")
        self.cli_status_var = tk.StringVar(value="未检测")
        self.agents_status_var = tk.StringVar(value="未检测")
        ttk.Label(status_grid, text="See Skill").grid(
            row=0,
            column=0,
            sticky="nw",
            pady=2,
        )
        ttk.Label(
            status_grid,
            textvariable=self.skill_status_var,
            wraplength=520,
            justify="left",
        ).grid(row=0, column=1, sticky="w", pady=2)
        ttk.Label(status_grid, text="全局 CLI").grid(
            row=1,
            column=0,
            sticky="nw",
            pady=2,
        )
        ttk.Label(
            status_grid,
            textvariable=self.cli_status_var,
            wraplength=520,
            justify="left",
        ).grid(row=1, column=1, sticky="w", pady=2)
        ttk.Label(status_grid, text="AGENTS 规则").grid(
            row=2,
            column=0,
            sticky="nw",
            pady=2,
        )
        ttk.Label(
            status_grid,
            textvariable=self.agents_status_var,
            justify="left",
        ).grid(row=2, column=1, sticky="w", pady=2)

        ttk.Checkbutton(
            parent,
            text="安装 / 更新时同时写入 ~/.codex/AGENTS.md 看图拒绝覆盖规则",
            variable=self.install_agents_var,
        ).pack(anchor="w", pady=(8, 4))

        buttons = ttk.Frame(parent)
        buttons.pack(anchor="w", pady=6)
        ttk.Button(
            buttons,
            text="安装 / 更新全局组件",
            command=self._install_all_from_gui,
        ).pack(side="left")
        ttk.Button(
            buttons,
            text="刷新状态",
            command=self._refresh_install_status,
        ).pack(side="left", padx=8)
        ttk.Button(
            buttons,
            text="检查本地视觉后端",
            command=self._check_local_from_gui,
        ).pack(side="left", padx=8)
        ttk.Button(
            buttons,
            text="打开 Skill 目录",
            command=self._open_skill_dir,
        ).pack(side="left", padx=8)
        ttk.Button(
            buttons,
            text="打开配置目录",
            command=self._open_config_dir,
        ).pack(side="left", padx=8)

        uninstall_box = ttk.LabelFrame(parent, text="卸载", padding=8)
        uninstall_box.pack(fill="x", pady=8)
        uninstall_labels = {
            "skill": "卸载 See Skill",
            "cli": "卸载全局 CLI（含 PATH 条目）",
            "agents": "移除 AGENTS.md 规则",
            "config": "删除配置文件",
            "credentials": "删除系统凭据 Key",
            "logs": "清空使用日志",
        }
        for index, key in enumerate(uninstall_labels):
            ttk.Checkbutton(
                uninstall_box,
                text=uninstall_labels[key],
                variable=self.uninstall_vars[key],
            ).grid(row=index // 3, column=index % 3, sticky="w", padx=6, pady=3)
        ttk.Button(
            uninstall_box,
            text="执行选定卸载",
            command=self._uninstall_from_gui,
        ).grid(row=2, column=0, sticky="w", pady=(6, 0))

        self.install_status = scrolledtext.ScrolledText(
            parent,
            height=10,
            state="disabled",
            wrap="word",
        )
        self.install_status.pack(fill="both", expand=True, pady=(8, 0))
        self._install_log("配置目录：" + str(onboard.config_file_path()))

    def _build_log_tab(self, parent: ttk.Frame) -> None:
        ttk.Label(
            parent,
            text="识图与安装使用日志",
            font=("", 13, "bold"),
        ).pack(anchor="w", pady=(0, 8))
        self.log_summary_var = tk.StringVar(value="")
        ttk.Label(
            parent,
            textvariable=self.log_summary_var,
            wraplength=680,
            justify="left",
        ).pack(anchor="w", pady=(0, 4))
        ttk.Label(
            parent,
            text=f"日志文件：{usage_log.log_file_path()}",
        ).pack(anchor="w", pady=(0, 6))

        controls = ttk.Frame(parent)
        controls.pack(anchor="w", pady=(0, 6))
        ttk.Button(controls, text="刷新日志", command=self._refresh_logs).pack(side="left")
        ttk.Button(
            controls,
            text="清空日志",
            command=self._clear_logs_from_gui,
        ).pack(side="left", padx=8)
        ttk.Checkbutton(
            controls,
            text="自动刷新（3 秒）",
            variable=self.auto_refresh_var,
        ).pack(side="left")

        self.log_text = scrolledtext.ScrolledText(
            parent,
            state="disabled",
            wrap="word",
        )
        self.log_text.pack(fill="both", expand=True)

    def _refresh_for_provider(self) -> None:
        provider = self.provider_var.get()
        label = PROVIDER_LABELS.get(provider, provider)
        self.root.title(f"{APP_TITLE} · {label}")

        values = current_values()
        spec = parse_media.PROVIDER_SPECS.get(provider)
        if spec is None:
            self._set_fields(api_key="", base_url="", image_model="", video_model="")
            self._set_fields_state(api_key="disabled", base_url="disabled", image_model="disabled", video_model="disabled")
            self._set_status("本地视觉 / OCR 不需要 API Key；视频分析仍需要云端 Key。")
            return

        api_key = ""
        base_url = values.get(spec["base_env"], "") or spec["base_url"]
        image_model = values.get(spec["model_env"], "") or spec["model"]
        video_model = values.get(spec["video_model_env"], "") or spec["video_model"] or image_model
        self._set_fields(api_key=api_key, base_url=base_url, image_model=image_model, video_model=video_model)

        needs_key = spec.get("requires_key", True)
        self._set_fields_state(
            api_key="normal" if needs_key else "disabled",
            base_url="normal",
            image_model="normal",
            video_model="normal",
        )
        if provider == "custom":
            self._set_status("自定义模型：请填写 OpenAI 兼容 API 地址、图片模型和 API Key。")
        elif not needs_key:
            self._set_status("该适配复用本机 CC Switch 代理，不需要单独 API Key。")
        else:
            self._set_status("API Key 留空时保留系统凭据库中已有的值。")

    def _set_fields(self, *, api_key: str, base_url: str, image_model: str, video_model: str) -> None:
        self.api_key_var.set(api_key)
        self.base_url_var.set(base_url)
        self.image_model_var.set(image_model)
        self.video_model_var.set(video_model)

    def _set_fields_state(
        self,
        *,
        api_key: str,
        base_url: str,
        image_model: str,
        video_model: str,
    ) -> None:
        self.field_entries["api_key"].config(state=api_key)
        self.field_entries["base_url"].config(state=base_url)
        self.field_entries["image_model"].config(state=image_model)
        self.field_entries["video_model"].config(state=video_model)

    def _mark_api_key_optional(self) -> None:
        # Placeholder for future inline validation; current copy is enough.
        return

    def _set_status(self, text: str) -> None:
        self.status.config(state="normal")
        self.status.delete("1.0", "end")
        self.status.insert("1.0", text)
        self.status.config(state="disabled")

    def _install_log(self, text: str) -> None:
        self.install_status.config(state="normal")
        self.install_status.insert("end", text.rstrip() + "\n")
        self.install_status.see("end")
        self.install_status.config(state="disabled")

    def _run_in_thread(
        self,
        operation: Callable[[], Any],
        on_success: Callable[[Any], None],
    ) -> None:
        def target() -> None:
            try:
                result = operation()
            except Exception as exc:  # GUI thread surfaces sanitized message below.
                self.root.after(0, lambda: self._show_error(exc))
            else:
                self.root.after(0, lambda: on_success(result))

        threading.Thread(target=target, daemon=True).start()

    def _show_error(self, exc: Exception) -> None:
        messagebox.showerror(APP_TITLE, onboard.safe_error(exc))
        self._set_status("操作失败：\n" + onboard.safe_error(exc))

    def _current_gui_plan(self) -> SavePlan:
        return build_save_plan(
            self.provider_var.get(),
            self.api_key_var.get(),
            self.base_url_var.get(),
            self.image_model_var.get(),
            self.video_model_var.get(),
            self.make_default_var.get(),
            current_values(),
        )

    def _plan_with_stored_credential(self) -> SavePlan:
        plan = self._current_gui_plan()
        if (
            not plan.api_key
            and plan.reference
            and plan.verify is not None
            and plan.verify.requires_key
        ):
            plan.api_key = secure_credentials.read(plan.reference)
        return plan

    def _save_from_gui(self) -> None:
        try:
            plan = self._plan_with_stored_credential()
        except Exception as exc:
            self._show_error(exc)
            return

        skip_check = self.skip_check_var.get()

        def operation() -> Path:
            if not skip_check:
                if plan.provider == "local":
                    onboard.verify_local()
                elif plan.verify is not None:
                    onboard.verify_provider(plan.verify)
            if plan.save_secret:
                secure_credentials.save(plan.reference, plan.api_key)
            return onboard.write_config(plan.values)

        self._set_status("正在保存并验证，请稍候...")
        self._run_in_thread(
            operation,
            lambda path: (
                self._set_status(f"配置完成：{path}\n" + self._status_snapshot(plan.provider)),
                messagebox.showinfo(APP_TITLE, f"配置完成：\n{path}"),
            ),
        )

    def _test_from_gui(self) -> None:
        try:
            plan = self._plan_with_stored_credential()
        except Exception as exc:
            self._show_error(exc)
            return

        if plan.provider == "local":
            operation: Callable[[], Any] = onboard.verify_local
        elif plan.verify is not None:
            operation = lambda: onboard.verify_provider(plan.verify)
        else:
            self._set_status("当前供应商没有可测试的云端配置。")
            return

        self._set_status("正在测试，请稍候...")
        self._run_in_thread(
            operation,
            lambda result: self._set_status(f"测试成功：{result}"),
        )

    def _install_all_from_gui(self) -> None:
        install_rule = self.install_agents_var.get()

        def operation() -> tuple[Path, str, Path, list[str], tuple[Path, bool] | None]:
            skill_path = onboard.install_skill()
            launcher, path_messages = onboard.install_cli()
            agents = onboard.install_agents_rule() if install_rule else None
            return (
                skill_path,
                onboard.bundled_version(),
                launcher,
                path_messages,
                agents,
            )

        self._install_log("正在安装 / 更新全局组件...")
        self._run_in_thread(operation, self._finish_install)

    def _finish_install(
        self,
        result: tuple[Path, str, Path, list[str], tuple[Path, bool] | None],
    ) -> None:
        skill_path, version, launcher, path_messages, agents = result
        self._install_log(f"See Skill 已安装 / 更新：{skill_path}（v{version}）")
        self._install_log(f"全局 CLI 已安装：{launcher}")
        for message in path_messages:
            self._install_log(message)
        if agents is not None:
            path, changed = agents
            self._install_log(
                f"看图拒绝覆盖：{'已写入' if changed else '已存在'} {path}"
                + ("；重启 Codex 后生效。" if changed else "")
            )
        messagebox.showinfo(
            APP_TITLE,
            "See Skill 与全局 CLI 已安装。\n"
            "新终端里可直接使用 see 命令，Codex 也识别本地 Skill。",
        )
        self._refresh_install_status()

    def _uninstall_from_gui(self) -> None:
        plan = UninstallPlan(
            skill=self.uninstall_vars["skill"].get(),
            cli=self.uninstall_vars["cli"].get(),
            agents=self.uninstall_vars["agents"].get(),
            config=self.uninstall_vars["config"].get(),
            credentials=self.uninstall_vars["credentials"].get(),
            logs=self.uninstall_vars["logs"].get(),
        )
        if not plan.ready():
            messagebox.showwarning(APP_TITLE, "请先勾选要卸载的项目。")
            return
        if not messagebox.askyesno(
            APP_TITLE,
            "将卸载：\n" + plan.summary() + "\n\n确定继续吗？",
        ):
            return

        def operation() -> dict[str, object]:
            return onboard.uninstall_integration(
                skill=plan.skill,
                cli=plan.cli,
                agents=plan.agents,
                config=plan.config,
                credentials=plan.credentials,
                logs=plan.logs,
            )

        self._install_log("正在卸载选定的全局组件...")
        self._run_in_thread(operation, self._finish_uninstall)

    def _finish_uninstall(self, summary: dict[str, object]) -> None:
        lines = []
        if "skill" in summary:
            lines.append(f"See Skill 卸载：{'完成' if summary['skill'] else '未安装'}")
        if "cli" in summary:
            lines.append(f"全局 CLI 卸载：{'完成' if summary['cli'] else '未安装'}")
        if "agents_rule" in summary:
            lines.append(f"AGENTS 规则移除：{'完成' if summary['agents_rule'] else '未写入'}")
        if "config" in summary:
            lines.append(f"配置文件删除：{'完成' if summary['config'] else '不存在'}")
        if "credentials_removed" in summary:
            removed = summary["credentials_removed"]
            lines.append(f"系统凭据删除：{len(removed) if isinstance(removed, list) else removed} 条")
        if "logs_cleared" in summary:
            lines.append(f"使用日志清空：{'完成' if summary['logs_cleared'] else '不存在'}")
        self._install_log("--- 卸载结果 ---")
        for line in lines:
            self._install_log(line)
        for error in summary.get("credential_errors", []):
            self._install_log(f"凭据删除失败：{error}")
        messagebox.showinfo(APP_TITLE, "卸载完成。\n" + "\n".join(lines))
        self._refresh_install_status()

    def _refresh_install_status(self) -> None:
        skill = onboard.skill_install_status()
        cli = onboard.cli_install_status()
        agents_path = onboard.user_agents_path()
        agents_text = agents_path.read_text(encoding="utf-8") if agents_path.exists() else ""
        agents_installed = onboard.agents_rule_installed(agents_text)

        if skill["installed"]:
            mark = "已安装（最新）" if skill["up_to_date"] else "已安装（可更新）"
            self.skill_status_var.set(
                f"{mark} · v{skill['version']}\n{skill['path']}"
            )
        else:
            self.skill_status_var.set("未安装")
        if cli["installed"]:
            path_state = "已在 PATH" if cli["on_path"] else "未在 PATH（重启终端生效）"
            self.cli_status_var.set(f"{path_state}\n{cli['path']}")
        else:
            self.cli_status_var.set("未安装")
        self.agents_status_var.set("已写入" if agents_installed else "未写入")
        self._install_log(
            f"状态已刷新：Skill {'v' + str(skill['version']) if skill['installed'] else '未安装'}；"
            f"CLI {'在 PATH' if cli.get('on_path') else '未安装'}；"
            f"AGENTS {'已写入' if agents_installed else '未写入'}"
        )

    def _open_skill_dir(self) -> None:
        path = onboard.skill_dest_dir()
        if not path.exists():
            messagebox.showwarning(APP_TITLE, "See Skill 尚未安装。")
            return
        opener = {
            "darwin": "open",
            "win32": "explorer",
        }.get(sys.platform, "xdg-open")
        subprocess.Popen([opener, str(path)])

    def _save_advanced_from_gui(self) -> None:
        try:
            advanced = advanced_values_from_gui(
                self.output_dir_var.get(),
                self.ocr_backend_var.get(),
                self.ocr_languages_var.get(),
                self.jobs_var.get(),
            )
            values = current_values()
            for key in ADVANCED_KEYS:
                values.pop(key, None)
            values.update(advanced)
            path = onboard.write_config(values)
        except Exception as exc:
            self._show_error(exc)
            return
        self._set_status(f"截图与本地选项已保存：\n{path}")

    def _load_advanced_values(self) -> None:
        output_dir, ocr_backend, ocr_languages, jobs = display_advanced_values()
        self.output_dir_var.set(output_dir)
        self.ocr_backend_var.set(ocr_backend)
        self.ocr_languages_var.set(ocr_languages)
        self.jobs_var.set(jobs)

    def _refresh_logs(self) -> None:
        entries = usage_log.read(200)
        summary = log_summary(entries)
        self.log_summary_var.set(
            f"最近 200 条：共 {summary['total']} 条；识图成功 {summary['success']} 次，"
            f"失败 {summary['failed']} 次；最近一次 {summary['last'] or '无'}"
        )
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        rendered = "\n".join(format_log_entry(item) for item in reversed(entries))
        self.log_text.insert("1.0", rendered or "暂无日志")
        self.log_text.config(state="disabled")
        self._schedule_log_refresh()

    def _schedule_log_refresh(self) -> None:
        try:
            self.root.after_cancel(self._log_after_id)
        except (AttributeError, tk.TclError):
            pass
        if self.auto_refresh_var.get():
            self._log_after_id = self.root.after(3000, self._refresh_logs)

    def _clear_logs_from_gui(self) -> None:
        if not messagebox.askyesno(APP_TITLE, "确定清空使用日志吗？"):
            return
        usage_log.clear()
        self._install_log("使用日志已清空。")
        self._refresh_logs()

    def _check_local_from_gui(self) -> None:
        self._run_in_thread(
            onboard.verify_local,
            lambda backend: self._install_log(f"本地图片分析可用：{backend}"),
        )

    def _open_config_dir(self) -> None:
        path = onboard.config_file_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        opener = {
            "darwin": "open",
            "win32": "explorer",
        }.get(sys.platform, "xdg-open")
        subprocess.Popen([opener, str(path.parent)])

    def _status_snapshot(self, provider: str) -> str:
        values = current_values()
        return (
            f"默认供应商：{values.get('SEE_PROVIDER', '未设置')}\n"
            f"当前配置供应商：{PROVIDER_LABELS.get(provider, provider)}"
        )

    def run(self) -> None:
        self.root.mainloop()


def main() -> int:
    if tk is None:
        print("[ERROR] 当前 Python 未安装 Tk，无法启动图形界面。", file=sys.stderr)
        return 1
    try:
        SeeGui().run()
    except tk.TclError as exc:
        print(f"[ERROR] 无法启动图形界面：{onboard.safe_error(exc)}", file=sys.stderr)
        print("请确认系统已安装 Tk，并运行于桌面会话中。", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
