//! Everything about Docker: finding it, asking whether the engine answers, starting Docker
//! Desktop, and — when it is missing — downloading the official installer and running it.

use crate::platform::{command, data_dir};
use crate::state::{Problem, Shared, INSTALL_DOCKER, INSTALL_WSL, RETRY};
#[cfg(windows)]
use crate::state::{CONTINUE, REBOOT};
use std::path::{Path, PathBuf};
use std::process::Output;
use std::thread::sleep;
use std::time::{Duration, Instant};

/// The docker CLI, or None when Docker is not installed. `WINCHICKEN_DOCKER` overrides the
/// lookup (tests set it to a missing path to rehearse the "not installed" branch).
pub fn cli() -> Option<PathBuf> {
    if let Ok(path) = std::env::var("WINCHICKEN_DOCKER") {
        let path = PathBuf::from(path);
        return path.exists().then_some(path);
    }
    let name = if cfg!(windows) { "docker.exe" } else { "docker" };
    if let Some(paths) = std::env::var_os("PATH") {
        for dir in std::env::split_paths(&paths) {
            let candidate = dir.join(name);
            if candidate.is_file() {
                return Some(candidate);
            }
        }
    }
    // Right after a Docker Desktop install the launcher's own PATH predates it.
    let defaults: &[&str] = if cfg!(windows) {
        &[r"C:\Program Files\Docker\Docker\resources\bin\docker.exe"]
    } else if cfg!(target_os = "macos") {
        &["/usr/local/bin/docker", "/Applications/Docker.app/Contents/Resources/bin/docker"]
    } else {
        &["/usr/bin/docker", "/usr/local/bin/docker"]
    };
    defaults.iter().map(PathBuf::from).find(|p| p.is_file())
}

pub fn run(docker: &Path, args: &[&str]) -> std::io::Result<Output> {
    crate::log(&format!("$ docker {}", args.join(" ")));
    let out = command(docker).args(args).output()?;
    let tail = |bytes: &[u8]| {
        let text = String::from_utf8_lossy(bytes);
        let lines: Vec<&str> = text.lines().collect();
        lines[lines.len().saturating_sub(15)..].join("\n")
    };
    if !out.stdout.is_empty() {
        crate::log(&tail(&out.stdout));
    }
    if !out.stderr.is_empty() {
        crate::log(&tail(&out.stderr));
    }
    Ok(out)
}

pub fn engine_ready(docker: &Path) -> bool {
    command(docker).args(["info", "--format", "{{.ServerVersion}}"]).output().map(|o| o.status.success()).unwrap_or(false)
}

fn docker_desktop_app() -> Option<PathBuf> {
    if cfg!(windows) {
        let p = PathBuf::from(r"C:\Program Files\Docker\Docker\Docker Desktop.exe");
        p.exists().then_some(p)
    } else if cfg!(target_os = "macos") {
        let p = PathBuf::from("/Applications/Docker.app");
        p.exists().then_some(p)
    } else {
        None
    }
}

/// Starts Docker Desktop if needed and waits (up to 6 min — a first start on a slow PC is long)
/// for the engine to answer.
pub fn start_and_wait(docker: &Path, shared: &Shared) -> Result<(), Problem> {
    if engine_ready(docker) {
        return Ok(());
    }
    match docker_desktop_app() {
        Some(app) if cfg!(windows) => {
            let _ = command(&app).spawn();
        }
        Some(_) => {
            let _ = command("open").args(["-g", "-a", "Docker"]).spawn();
        }
        None => crate::log("Docker Desktop introuvable : on attend que le service Docker réponde."),
    }
    let started = Instant::now();
    while started.elapsed() < Duration::from_secs(360) {
        if engine_ready(docker) {
            return Ok(());
        }
        let secs = started.elapsed().as_secs();
        shared.lock().unwrap().set("docker_start", crate::state::StepState::Running, &format!("Docker démarre… ({secs} s)"));
        sleep(Duration::from_secs(3));
    }
    let wsl_hint = cfg!(windows) && !wsl_installed();
    Err(if wsl_hint {
        Problem::new(
            "wsl_needed",
            "WSL doit être installé",
            "Docker a besoin d'un composant de Windows appelé WSL. Cliquez sur « Installer WSL » \
             (Windows demandera l'autorisation : répondez Oui), puis redémarrez l'ordinateur. \
             Winchicken reprendra tout seul après le redémarrage.",
            &[INSTALL_WSL, RETRY],
        )
    } else {
        Problem::new(
            "docker_not_starting",
            "Docker ne démarre pas",
            "Docker est installé mais ne répond pas après 6 minutes. Ouvrez « Docker Desktop » depuis \
             le menu Démarrer et lisez son message : s'il demande d'accepter des conditions ou de \
             mettre à jour WSL, faites-le, puis cliquez sur Réessayer. S'il parle de virtualisation, \
             elle doit être activée dans le BIOS du PC (voir « Détails techniques »).",
            &[RETRY],
        )
    })
}

fn wsl_installed() -> bool {
    command("wsl").arg("--status").output().map(|o| o.status.success()).unwrap_or(false)
}

/// Runs `program args…` elevated on Windows (one UAC prompt) and returns its exit code, or the
/// problem to show when the prompt was refused.
#[cfg(windows)]
fn run_elevated(program: &str, args: &[&str]) -> Result<i32, Problem> {
    let quoted: Vec<String> = args.iter().map(|a| format!("'{a}'")).collect();
    let script = format!(
        "try {{ $p = Start-Process -FilePath '{program}' -ArgumentList {} -Verb RunAs -Wait -PassThru; exit $p.ExitCode }} catch {{ Write-Output 'REFUSED'; exit 1223 }}",
        quoted.join(",")
    );
    crate::log(&format!("(élevé) {program} {}", args.join(" ")));
    let out = command("powershell").args(["-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", &script]).output()
        .map_err(|e| Problem::new("elevation_failed", "Impossible de lancer l'installation", &format!("PowerShell n'a pas pu être lancé ({e})."), &[RETRY]))?;
    let code = out.status.code().unwrap_or(-1);
    if code == 1223 || String::from_utf8_lossy(&out.stdout).contains("REFUSED") {
        return Err(Problem::new(
            "uac_refused",
            "Autorisation refusée",
            "Windows a demandé l'autorisation d'installer et elle a été refusée (ou la fenêtre a été \
             fermée). Cliquez de nouveau sur le bouton et répondez « Oui » quand Windows le demande.",
            &[INSTALL_DOCKER, RETRY],
        ));
    }
    Ok(code)
}

#[cfg_attr(not(any(windows, target_os = "macos")), allow(dead_code))]
/// Downloads `url` to `dest` with the system curl (Windows 10+ and macOS ship it), resuming a
/// partial file, and reports progress on the page.
fn download(url: &str, dest: &Path, shared: &Shared) -> Result<(), Problem> {
    let curl = if cfg!(windows) { "curl.exe" } else { "curl" };
    let total = command(curl).args(["-sIL", url]).output().ok().and_then(|o| {
        String::from_utf8_lossy(&o.stdout)
            .lines()
            .filter_map(|l| l.to_ascii_lowercase().strip_prefix("content-length:").map(|v| v.trim().to_string()))
            .filter_map(|v| v.parse::<u64>().ok())
            .last()
    });
    crate::log(&format!("téléchargement {url} ({} octets)", total.unwrap_or(0)));
    let mut child = command(curl)
        .args(["-L", "--fail", "--retry", "5", "-C", "-", "-o"])
        .arg(dest)
        .arg(url)
        .spawn()
        .map_err(|e| Problem::new("download_failed", "Le téléchargement n'a pas pu démarrer", &format!("curl introuvable ({e})."), &[INSTALL_DOCKER]))?;
    loop {
        let done = std::fs::metadata(dest).map(|m| m.len()).unwrap_or(0);
        shared.lock().unwrap().download = Some((done, total.unwrap_or(0)));
        match child.try_wait() {
            Ok(Some(status)) => {
                shared.lock().unwrap().download = None;
                if status.success() {
                    return Ok(());
                }
                return Err(Problem::new(
                    "download_failed",
                    "Le téléchargement de Docker a échoué",
                    "La connexion Internet a été coupée ou est trop faible. Vérifiez la connexion puis \
                     cliquez sur « Installer Docker » : le téléchargement reprendra là où il s'est arrêté.",
                    &[INSTALL_DOCKER],
                ));
            }
            Ok(None) => sleep(Duration::from_millis(700)),
            Err(_) => return Err(Problem::new("download_failed", "Le téléchargement de Docker a échoué", "Erreur inattendue.", &[INSTALL_DOCKER])),
        }
    }
}

/// "Installer Docker": official installer, one permission prompt, then usually a restart.
pub fn install(shared: &Shared) -> Result<(), Problem> {
    let downloads = data_dir().join("downloads");
    let _ = std::fs::create_dir_all(&downloads);

    #[cfg(windows)]
    {
        let installer = downloads.join("DockerDesktopInstaller.exe");
        shared.lock().unwrap().set("docker", crate::state::StepState::Running, "Téléchargement de Docker Desktop (environ 600 Mo)…");
        download("https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe", &installer, shared)?;
        shared.lock().unwrap().set("docker", crate::state::StepState::Running, "Installation de Docker Desktop… Windows va demander l'autorisation : répondez Oui. Cela prend 5 à 10 minutes.");
        let code = run_elevated(&installer.to_string_lossy(), &["install", "--quiet", "--accept-license", "--backend=wsl-2"])?;
        crate::log(&format!("installateur Docker terminé, code {code}"));
        if code != 0 && code != 3010 {
            return Err(Problem::new(
                "docker_install_failed",
                "L'installation de Docker a échoué",
                &format!("L'installateur de Docker s'est arrêté avec le code {code}. Redémarrez l'ordinateur puis \
                          cliquez sur « Installer Docker ». Si cela recommence, copiez le rapport (Détails techniques) \
                          et envoyez-le au support."),
                &[INSTALL_DOCKER, REBOOT],
            ));
        }
        crate::platform::register_resume_after_reboot();
        return Err(Problem::new(
            "reboot_needed",
            "Redémarrage nécessaire",
            "Docker est installé. Windows doit redémarrer pour terminer. Enregistrez votre travail en \
             cours, puis cliquez sur « Redémarrer l'ordinateur » : Winchicken reprendra tout seul \
             après le redémarrage.",
            &[REBOOT, CONTINUE],
        ));
    }

    #[cfg(target_os = "macos")]
    {
        let arch = command("uname").arg("-m").output().map(|o| String::from_utf8_lossy(&o.stdout).trim().to_string()).unwrap_or_default();
        let url = if arch == "arm64" {
            "https://desktop.docker.com/mac/main/arm64/Docker.dmg"
        } else {
            "https://desktop.docker.com/mac/main/amd64/Docker.dmg"
        };
        let dmg = downloads.join("Docker.dmg");
        shared.lock().unwrap().set("docker", crate::state::StepState::Running, "Téléchargement de Docker Desktop (environ 600 Mo)…");
        download(url, &dmg, shared)?;
        shared.lock().unwrap().set("docker", crate::state::StepState::Running, "Installation de Docker Desktop… macOS va demander le mot de passe de l'ordinateur.");
        let user = std::env::var("USER").unwrap_or_default();
        let shell = format!(
            "hdiutil attach -nobrowse -quiet '{}' -mountpoint /Volumes/WinchickenDocker && \
             /Volumes/WinchickenDocker/Docker.app/Contents/MacOS/install --accept-license --user={user}; \
             s=$?; hdiutil detach -quiet /Volumes/WinchickenDocker; exit $s",
            dmg.display()
        );
        let script = format!("do shell script \"{}\" with administrator privileges", shell.replace('"', "\\\""));
        let out = command("osascript").args(["-e", &script]).output();
        let ok = out.as_ref().map(|o| o.status.success()).unwrap_or(false);
        if !ok {
            let refused = out.map(|o| String::from_utf8_lossy(&o.stderr).contains("-128")).unwrap_or(false);
            return Err(if refused {
                Problem::new("auth_refused", "Autorisation refusée", "Le mot de passe de l'ordinateur est nécessaire pour installer Docker. Cliquez de nouveau sur « Installer Docker ».", &[INSTALL_DOCKER])
            } else {
                Problem::new("docker_install_failed", "L'installation de Docker a échoué", "Copiez le rapport (Détails techniques) et envoyez-le au support.", &[INSTALL_DOCKER, RETRY])
            });
        }
        return Ok(());
    }

    #[allow(unreachable_code)]
    {
        let _ = (shared, downloads);
        Err(Problem::new(
            "docker_manual",
            "Installez Docker",
            "Sur Linux, installez Docker Engine avec le gestionnaire de paquets de votre distribution \
             (voir docs.docker.com/engine/install), puis cliquez sur Réessayer.",
            &[RETRY],
        ))
    }
}

/// "Installer WSL" (Windows): the component Docker Desktop runs on. Needs a restart after.
pub fn install_wsl() -> Result<(), Problem> {
    #[cfg(windows)]
    {
        let code = run_elevated("wsl.exe", &["--install", "--no-distribution"])?;
        crate::log(&format!("wsl --install terminé, code {code}"));
        crate::platform::register_resume_after_reboot();
        return Err(Problem::new(
            "reboot_needed",
            "Redémarrage nécessaire",
            "WSL est installé. Redémarrez l'ordinateur : Winchicken reprendra tout seul après le redémarrage.",
            &[REBOOT, CONTINUE],
        ));
    }
    #[allow(unreachable_code)]
    Ok(())
}
