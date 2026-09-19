# SeeGui 桌面端打包

`see/scripts/gui.py` 是 Tkinter 配置、安装与日志界面。桌面端通过 PyInstaller 打包，安装包内携带完整 See Skill 资源，因此可以离线完成全局安装与卸载。CI 会产出：

- Windows：`SeeGui-<version>-windows-x64-setup.exe`（NSIS 安装包）
- macOS：`SeeGui-<version>-macos-<arch>.dmg`
- Linux：`SeeGui-<version>-linux-x86_64.AppImage`

推送 `v*` 版本 tag（例如 `v1.0.20260918`）时，CI 会复用同一套三平台构建并自动创建/更新 GitHub Release，附上三个安装包。同一版本号重新打 tag 会替换旧 Release 的二进制：

```bash
git tag v1.0.20260918
git push origin v1.0.20260918
```

生成的 SeeGui 提供“配置 / 安装 / 日志”三个页签：配置供应商与截图选项，一键安装 See Skill 和全局 `see` CLI，随时卸载选定的全局组件，并监控识图与安装日志。

本机构建：

```bash
python3 -m pip install -r see/scripts/requirements-credentials.txt -r packaging/requirements-build.txt
python3 packaging/build_installers.py --installer nsis   # Windows
python3 packaging/build_installers.py --installer dmg    # macOS
python3 packaging/build_installers.py --installer appimage  # Linux
```

Windows 构建需要 NSIS（`makensis` 在 PATH 中），Linux 构建会下载 AppImageKit，macOS 构建使用系统 `hdiutil`。
