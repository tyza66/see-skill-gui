# SeeGui 桌面端打包

`see/scripts/gui.py` 是 Tkinter 配置与安装界面。桌面端通过 PyInstaller 打包，CI 会产出：

- Windows：`SeeGui-<version>-windows-x64-setup.exe`（NSIS 安装包）
- macOS：`SeeGui-<version>-macos-<arch>.dmg`
- Linux：`SeeGui-<version>-linux-x86_64.AppImage`

推送 `v*` 版本 tag（例如 `v1.0.0`）时，CI 会复用同一套三平台构建并自动创建 GitHub Release，附上三个安装包：

```bash
git tag v1.0.0
git push origin v1.0.0
```

本机构建：

```bash
python3 -m pip install -r see/scripts/requirements-credentials.txt -r packaging/requirements-build.txt
python3 packaging/build_installers.py --installer nsis   # Windows
python3 packaging/build_installers.py --installer dmg    # macOS
python3 packaging/build_installers.py --installer appimage  # Linux
```

Windows 构建需要 NSIS（`makensis` 在 PATH 中），Linux 构建会下载 AppImageKit，macOS 构建使用系统 `hdiutil`。
