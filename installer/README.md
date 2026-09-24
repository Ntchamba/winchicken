# Winchicken installers

What a farm downloads from the landing page (a separate project) to run Winchicken on its own PC,
with Docker, typing no command. Windows first; macOS (`.pkg`) next.

## Pieces

| Path | Role |
|---|---|
| `../docker-compose.prod.yml` | The farm stack: nginx + built app on one port, gunicorn, one Celery worker with beat embedded, Postgres, Redis, backups. ~400 MB RAM measured. |
| `scripts/build-bundle.sh` | Builds the versioned images and packs them (≈250 MB) with the compose file and `VERSION` into `resources/`. |
| `launcher/` | `winchicken.exe` — the program behind the desktop icon (Rust, ~650 KB). Serves a French setup page on `127.0.0.1:47823` and runs the steps below. |
| `windows/winchicken.nsi` | The Windows installer (NSIS): French wizard, per-user install, shortcuts, uninstaller. |
| `scripts/build-windows.sh` | Builds `Winchicken-Setup-<version>.exe` on Linux with Docker only. |
| `../.github/workflows/installer.yml` | Runs `build-windows.sh` on GitHub (push to `installer-build`, a `v*` tag, or by hand) and attaches the `.exe` to the run. |

The version is `frontend/package.json` → `version` (the number the app shows in its sidebar).
Bump it for every release: the launcher treats a different version as an upgrade.

## Building

```bash
installer/scripts/build-windows.sh            # -> installer/dist/Winchicken-Setup-<version>.exe
```

A local build packs the **working tree**; the GitHub build packs the committed code. Ship the
GitHub one.

## What the launcher does (every launch, each step idempotent)

1. **Machine** — ≥10 GB free disk (blocks), RAM under 6 GB (warns only).
2. **Docker installed?** If not: "Installer Docker" downloads the official Docker Desktop
   installer (resumable, progress shown), runs it with one Windows permission prompt
   (`install --quiet --accept-license --backend=wsl-2`), then offers a restart and resumes by
   itself after it (`RunOnce`). macOS: admin password prompt. Linux: instructions.
3. **Docker running** — starts Docker Desktop, waits up to 6 min. First time on Windows it writes
   `%USERPROFILE%\.wslconfig` with `memory=2GB` unless the file already exists.
4. **Images** — loads the bundled archive only if a tag is missing (no internet needed).
5. **Settings** — `%LOCALAPPDATA%\Winchicken\.env` written **once**: random `SECRET_KEY` and
   `DB_PASSWORD`, first free port from 8080, Web Push keys. Later only `WINCHICKEN_VERSION` moves
   (a new DB password would lock the app out of its own database).
6. **Backup before an upgrade** — `backup_db` in the running stack; if it fails the upgrade stops.
7. **Start** — `docker compose -p winchicken-prod … up -d --no-build --pull never`.
8. **Ready** — waits for `/api/health/`, shows the farm-network address + QR code for phones,
   then opens Winchicken. An everyday launch with everything already up skips straight to
   opening the app.

Every failure is a French explanation with the buttons that fix it; the raw log is behind
"Détails techniques" (also `%LOCALAPPDATA%\Winchicken\launcher.log`) with "Copier le rapport".

**Updates**: download the new installer and run it over the old one. Data, settings and backups
are kept; the launcher backs up, then switches the images.

**Uninstall** stops the services and removes the program; the farm's data (Docker volumes) and
`%LOCALAPPDATA%\Winchicken` are kept so a reinstall finds them. To erase everything as well:
`docker compose -p winchicken-prod down -v` and delete that folder.

## Signing

Not signed yet (decision 2026-09-24). Windows SmartScreen shows a warning on the first run;
the landing page must explain it (text below). Signing later needs an Authenticode certificate
(~$200–500/year).

## Texte pour la page de téléchargement (Windows)

> **Installer Winchicken sur le PC de la ferme (Windows 10 ou 11, 64 bits)**
>
> 1. Téléchargez `Winchicken-Setup.exe` (environ 260 Mo).
> 2. Double-cliquez dessus. Windows peut afficher « Windows a protégé votre ordinateur » :
>    cliquez sur **Informations complémentaires**, puis **Exécuter quand même**.
> 3. Cliquez sur **Suivant**, puis **Terminer** en laissant « Lancer Winchicken » coché.
> 4. Winchicken s'ouvre dans votre navigateur et termine l'installation tout seul.
>    Si Docker n'est pas installé, la page vous guide (10 à 20 minutes, connexion Internet
>    nécessaire, un redémarrage).
> 5. Les téléphones de la ferme (même Wi-Fi) ouvrent l'adresse affichée à la fin, ou scannent
>    le QR code.
>
> Configuration conseillée : 8 Go de mémoire (4 Go fonctionne, plus lentement), 10 Go d'espace
> disque libre, la virtualisation activée dans le BIOS.
