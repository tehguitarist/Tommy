; Tommy VST3 installer (NSIS). Windows has no AU format, so there's no plugin-type choice
; here — VST3 only, installed to the shared system VST3 folder.
;
; Build with (from repo root, after building Tommy_VST3):
;   makensis /DVERSION=0.7.0 /DARTEFACTS_DIR=build\Tommy_artefacts\Release\VST3 installer\windows\Tommy.nsi
;
; ARTEFACTS_DIR should point at the directory CONTAINING Tommy.vst3 (i.e. the VST3 release
; output folder), not Tommy.vst3 itself.

!ifndef VERSION
  !define VERSION "0.0.0"
!endif
!ifndef ARTEFACTS_DIR
  !define ARTEFACTS_DIR "..\..\build\Tommy_artefacts\Release\VST3"
!endif

Name "Tommy"
OutFile "Tommy-Windows-v${VERSION}-Installer.exe"
InstallDir "$COMMONFILES64\VST3"
RequestExecutionLevel admin
SetCompressor /SOLID lzma

Page directory
Page instfiles
UninstPage uninstConfirm
UninstPage instfiles

Section "Tommy VST3 Plugin" SecVST3
    SetOutPath "$INSTDIR\Tommy.vst3"
    File /r "${ARTEFACTS_DIR}\Tommy.vst3\*.*"

    WriteUninstaller "$INSTDIR\Tommy.vst3\Uninstall-Tommy.exe"

    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Tommy" \
        "DisplayName" "Tommy VST3"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Tommy" \
        "UninstallString" "$INSTDIR\Tommy.vst3\Uninstall-Tommy.exe"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Tommy" \
        "DisplayVersion" "${VERSION}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Tommy" \
        "Publisher" "Leigh Pierce"
SectionEnd

Section "Uninstall"
    RMDir /r "$INSTDIR\Tommy.vst3"
    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Tommy"
SectionEnd
