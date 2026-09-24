; Winchicken — Windows installer (NSIS 3). Built by .github/workflows/installer.yml:
;   makensis -DVERSION=1.0.0 -DBUNDLE=<dir with resources\> -DLAUNCHER=<winchicken-launcher.exe> -DOUTDIR=<dir> winchicken.nsi
;
; Per-user install (no administrator rights needed for Winchicken itself — only Docker Desktop's
; own installer asks, later, from the launcher). The installer only copies files and creates
; shortcuts; everything else (Docker, images, settings, start) is the launcher's job, shown
; step by step in the browser, which is why "Lancer Winchicken" is ticked on the last page.

Unicode true

!ifndef VERSION
  !error "VERSION manquant. Utilisation : makensis -DVERSION=x.y.z -DBUNDLE=<dossier> -DLAUNCHER=<exe> -DOUTDIR=<dossier> winchicken.nsi"
!endif
!ifndef BUNDLE
  !error "BUNDLE manquant. Utilisation : makensis -DVERSION=x.y.z -DBUNDLE=<dossier> -DLAUNCHER=<exe> -DOUTDIR=<dossier> winchicken.nsi"
!endif
!ifndef LAUNCHER
  !error "LAUNCHER manquant. Utilisation : makensis -DVERSION=x.y.z -DBUNDLE=<dossier> -DLAUNCHER=<exe> -DOUTDIR=<dossier> winchicken.nsi"
!endif
!ifndef OUTDIR
  !error "OUTDIR manquant. Utilisation : makensis -DVERSION=x.y.z -DBUNDLE=<dossier> -DLAUNCHER=<exe> -DOUTDIR=<dossier> winchicken.nsi"
!endif

!include "MUI2.nsh"
!include "x64.nsh"
!include "WinVer.nsh"

!define UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\Winchicken"

Name "Winchicken"
OutFile "${OUTDIR}\Winchicken-Setup-${VERSION}.exe"
InstallDir "$LOCALAPPDATA\Programs\Winchicken"
InstallDirRegKey HKCU "Software\Winchicken" "InstallDir"
RequestExecutionLevel user
; Not /SOLID: the images archive is already gzip-compressed and is stored as-is (SetCompress off
; below), which solid mode would not allow.
SetCompressor lzma
BrandingText "Winchicken ${VERSION}"

VIProductVersion "${VERSION}.0"
VIAddVersionKey /LANG=1036 "ProductName" "Winchicken"
VIAddVersionKey /LANG=1036 "FileDescription" "Installation de Winchicken"
VIAddVersionKey /LANG=1036 "ProductVersion" "${VERSION}"
VIAddVersionKey /LANG=1036 "FileVersion" "${VERSION}"
VIAddVersionKey /LANG=1036 "LegalCopyright" "Winchicken"

!define MUI_ICON "winchicken.ico"
!define MUI_UNICON "winchicken.ico"
!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TITLE "Installation de Winchicken ${VERSION}"
!define MUI_WELCOMEPAGE_TEXT "Winchicken va être installé sur cet ordinateur.$\r$\n$\r$\nÀ la fin, Winchicken s'ouvrira dans votre navigateur et terminera l'installation tout seul (environ 1 minute). Si Docker n'est pas encore installé, la page vous guidera : comptez alors 10 à 20 minutes et une connexion Internet.$\r$\n$\r$\nCliquez sur Suivant pour continuer."
!define MUI_FINISHPAGE_TITLE "Winchicken est installé"
!define MUI_FINISHPAGE_TEXT "Laissez la case cochée et cliquez sur Terminer : Winchicken s'ouvre dans votre navigateur et termine l'installation.$\r$\n$\r$\nEnsuite, l'icône Winchicken du Bureau ouvre l'application."
!define MUI_FINISHPAGE_RUN "$INSTDIR\winchicken.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Lancer Winchicken maintenant"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "French"

Function .onInit
  ${IfNot} ${RunningX64}
    MessageBox MB_ICONSTOP "Winchicken nécessite une version 64 bits de Windows."
    Abort
  ${EndIf}
  ${IfNot} ${AtLeastWin10}
    MessageBox MB_ICONSTOP "Winchicken nécessite Windows 10 ou Windows 11."
    Abort
  ${EndIf}
FunctionEnd

Section "Winchicken"
  ; An older launcher may still be serving its page; its exe would be locked.
  nsExec::Exec 'taskkill /IM winchicken.exe /F'

  SetOutPath "$INSTDIR"
  File "/oname=winchicken.exe" "${LAUNCHER}"
  File "winchicken.ico"

  SetOutPath "$INSTDIR\resources"
  File "${BUNDLE}\resources\docker-compose.prod.yml"
  File "${BUNDLE}\resources\VERSION"
  SetOutPath "$INSTDIR\resources\images"
  File "${BUNDLE}\resources\images\images.txt"
  SetCompress off
  File "${BUNDLE}\resources\images\winchicken-images.tar.gz"
  SetCompress auto

  SetOutPath "$INSTDIR"
  CreateShortCut "$DESKTOP\Winchicken.lnk" "$INSTDIR\winchicken.exe" "" "$INSTDIR\winchicken.ico"
  CreateDirectory "$SMPROGRAMS\Winchicken"
  CreateShortCut "$SMPROGRAMS\Winchicken\Winchicken.lnk" "$INSTDIR\winchicken.exe" "" "$INSTDIR\winchicken.ico"
  CreateShortCut "$SMPROGRAMS\Winchicken\Désinstaller Winchicken.lnk" "$INSTDIR\uninstall.exe"

  WriteUninstaller "$INSTDIR\uninstall.exe"
  WriteRegStr HKCU "Software\Winchicken" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayName" "Winchicken"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "${UNINST_KEY}" "Publisher" "Winchicken"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayIcon" "$INSTDIR\winchicken.ico"
  WriteRegStr HKCU "${UNINST_KEY}" "UninstallString" '"$INSTDIR\uninstall.exe"'
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoRepair" 1
SectionEnd

Section "Uninstall"
  nsExec::Exec 'taskkill /IM winchicken.exe /F'
  ; Stop Winchicken's services. Their Docker volumes (the farm's database and backups) and the
  ; settings in %LOCALAPPDATA%\Winchicken are kept on purpose: uninstalling must never be the
  ; way a farm loses its records. Reinstalling picks them up again.
  nsExec::Exec '"$PROGRAMFILES64\Docker\Docker\resources\bin\docker.exe" compose -p winchicken-prod down'

  Delete "$DESKTOP\Winchicken.lnk"
  RMDir /r "$SMPROGRAMS\Winchicken"
  RMDir /r "$INSTDIR\resources"
  Delete "$INSTDIR\winchicken.exe"
  Delete "$INSTDIR\winchicken.ico"
  Delete "$INSTDIR\uninstall.exe"
  RMDir "$INSTDIR"
  DeleteRegKey HKCU "${UNINST_KEY}"
  DeleteRegKey HKCU "Software\Winchicken"

  MessageBox MB_ICONINFORMATION "Winchicken est désinstallé.$\r$\n$\r$\nLes données de la ferme sont conservées : réinstaller Winchicken les retrouve."
SectionEnd
