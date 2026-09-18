#!/usr/bin/env python3
"""Tkinter GUI for configuring and installing see."""

from __future__ import annotations

import os
import subprocess
import sys
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


@dataclass
class SavePlan:
    provider: str
    values: dict[str, str]
    verify: parse_media.Provider | None
    api_key: str
    reference: str
    save_secret: bool


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

        self._build_ui()
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
        notebook.add(config_tab, text="配置")
        notebook.add(install_tab, text="安装 / 状态")

        self._build_config_tab(config_tab)
        self._build_install_tab(install_tab)

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

        self.status = scrolledtext.ScrolledText(parent, height=16, state="disabled", wrap="word")
        self.status.pack(fill="both", expand=True, pady=8)

    def _build_install_tab(self, parent: ttk.Frame) -> None:
        heading = ttk.Label(
            parent,
            text="Codex 用户指令与本地能力检查",
            font=("", 13, "bold"),
        )
        heading.pack(anchor="w", pady=(0, 12))

        ttk.Checkbutton(
            parent,
            text="安装 / 更新 ~/.codex/AGENTS.md 的看图拒绝覆盖规则",
            variable=self.install_agents_var,
        ).pack(anchor="w", pady=4)

        buttons = ttk.Frame(parent)
        buttons.pack(anchor="w", pady=10)
        ttk.Button(buttons, text="执行安装 / 更新", command=self._install_from_gui).pack(side="left")
        ttk.Button(buttons, text="检查本地视觉后端", command=self._check_local_from_gui).pack(
            side="left",
            padx=8,
        )
        ttk.Button(buttons, text="打开配置目录", command=self._open_config_dir).pack(side="left")

        self.install_status = scrolledtext.ScrolledText(parent, height=18, state="disabled", wrap="word")
        self.install_status.pack(fill="both", expand=True, pady=10)
        self._install_log("配置目录：" + str(onboard.config_file_path()))

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

    def _install_from_gui(self) -> None:
        install_rule = self.install_agents_var.get()

        def operation() -> tuple[Path, bool] | None:
            if not install_rule:
                return None
            return onboard.install_agents_rule()

        self._run_in_thread(
            operation,
            lambda result: self._install_log(
                "未写入全局指令。"
                if result is None
                else (
                    f"{'已写入' if result[1] else '已存在'}看图拒绝覆盖：{result[0]}"
                    + ("；重启 Codex 后生效。" if result[1] else "")
                )
            ),
        )

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
