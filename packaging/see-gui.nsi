; SeeGui Windows installer built with NSIS.
Unicode True
!include "MUI2.nsh"

!ifndef VERSION
  !define VERSION "1.0.20260918"
!endif
!ifndef OUTPUT
  !define OUTPUT "..\dist\SeeGui-${VERSION}-windows-x64-setup.exe"
!endif

Name "SeeGui"
OutFile "${OUTPUT}"
InstallDir "$LOCALAPPDATA\Programs\SeeGui"
RequestExecutionLevel user
SetCompressor /SOLID lzma

!define MUI_ABORTWARNING
!define MUI_ICON "${NSISDIR}\Contrib\Graphics\Icons\modern-install.ico"
!define MUI_UNICON "${NSISDIR}\Contrib\Graphics\Icons\modern-uninstall.ico"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "SimpChinese"
!insertmacro MUI_LANGUAGE "English"

Section "Install" SecMain
  SetOutPath "$INSTDIR"
  File /oname=SeeGui.exe "..\dist\SeeGui.exe"
  CreateDirectory "$SMPROGRAMS\SeeGui"
  CreateShortcut "$SMPROGRAMS\SeeGui\SeeGui.lnk" "$INSTDIR\SeeGui.exe"
  CreateShortcut "$DESKTOP\SeeGui.lnk" "$INSTDIR\SeeGui.exe"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SeeGui" "DisplayName" "SeeGui"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SeeGui" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SeeGui" "Publisher" "see-skill"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SeeGui" "UninstallString" '"$INSTDIR\Uninstall.exe"'
SectionEnd

Section "Uninstall"
  Delete "$INSTDIR\SeeGui.exe"
  Delete "$INSTDIR\Uninstall.exe"
  Delete "$DESKTOP\SeeGui.lnk"
  Delete "$SMPROGRAMS\SeeGui\SeeGui.lnk"
  RMDir "$SMPROGRAMS\SeeGui"
  RMDir "$INSTDIR"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SeeGui"
SectionEnd
