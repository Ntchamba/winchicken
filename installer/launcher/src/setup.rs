//! The setup itself, as ordered, idempotent steps: every launch walks the same list, and a step
//! that has nothing to do is quick (Docker already running, images already loaded, .env already
//! written). That is also what makes "Réessayer" and the post-reboot resume safe.

use crate::docker;
use crate::platform::{self, data_dir, resources_dir};
use crate::state::{Problem, Ready, Shared, StepState, INSTALL_DOCKER, RETRY};
use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::thread::sleep;
use std::time::{Duration, Instant};

const PROJECT: &str = "winchicken-prod";
const MIN_FREE_DISK: u64 = 10 * 1024 * 1024 * 1024;

pub fn version() -> String {
    std::fs::read_to_string(resources_dir().join("VERSION")).map(|v| v.trim().to_string()).unwrap_or_else(|_| "dev".into())
}

fn step(shared: &Shared, id: &str, state: StepState, detail: &str) {
    crate::log(&format!("[{id}] {detail}"));
    shared.lock().unwrap().set(id, state, detail);
}

fn fail(shared: &Shared, id: &str, problem: Problem) -> Problem {
    step(shared, id, StepState::Failed, &problem.title);
    problem
}

/// Runs every step. Ok(()) = Winchicken answers; `Status.ready` then holds its addresses.
pub fn run(shared: &Shared) -> Result<(), Problem> {
    let data = data_dir();
    std::fs::create_dir_all(&data).map_err(|e| Problem::new("data_dir", "Dossier de données inaccessible", &format!("{} : {e}", data.display()), &[RETRY]))?;

    // 1. The machine.
    step(shared, "check", StepState::Running, "Espace disque et mémoire…");
    if let Some(free) = platform::free_disk_bytes(&data) {
        if free < MIN_FREE_DISK {
            return Err(fail(shared, "check", Problem::new(
                "disk_low",
                "Espace disque insuffisant",
                &format!("Winchicken et Docker ont besoin d'au moins 10 Go libres ; il reste {:.1} Go. \
                          Libérez de la place (Corbeille, dossier Téléchargements, vidéos), puis cliquez sur Réessayer.",
                         free as f64 / 1e9),
                &[RETRY],
            )));
        }
    }
    let ram_note = match platform::total_ram_bytes() {
        Some(ram) if ram < 6 * 1024 * 1024 * 1024 => "Mémoire : 4 Go — ça fonctionne, fermez les autres programmes pour que ce soit plus rapide.",
        _ => "OK",
    };
    step(shared, "check", StepState::Done, ram_note);

    // 2. Docker installed?
    step(shared, "docker", StepState::Running, "Recherche de Docker…");
    let Some(docker) = docker::cli() else {
        let how = if cfg!(windows) {
            "Windows demandera l'autorisation (répondez Oui) puis un redémarrage — Winchicken reprendra tout seul."
        } else if cfg!(target_os = "macos") {
            "macOS demandera le mot de passe de l'ordinateur, puis Docker s'ouvrira : acceptez ses conditions."
        } else {
            "Sur Linux, la page vous indiquera comment l'installer."
        };
        return Err(fail(shared, "docker", Problem::new(
            "docker_missing",
            "Docker n'est pas installé",
            &format!("Winchicken fonctionne grâce à Docker, un logiciel gratuit. Cliquez sur « Installer Docker » : \
                      le téléchargement fait environ 600 Mo et l'installation prend 10 à 20 minutes. {how}"),
            &[INSTALL_DOCKER, crate::state::Action { id: "retry", label: "J'ai installé Docker moi-même" }],
        )));
    };
    step(shared, "docker", StepState::Done, &docker.display().to_string());

    // 3. Docker running (and, first time on Windows, capped so it leaves the PC room).
    step(shared, "docker_start", StepState::Running, "Démarrage de Docker…");
    cap_wsl_memory();
    docker::start_and_wait(&docker, shared).map_err(|p| fail(shared, "docker_start", p))?;
    step(shared, "docker_start", StepState::Done, "Docker répond");

    // 4. Images, from the installer itself (no internet needed).
    let version = version();
    step(shared, "images", StepState::Running, "Vérification des images…");
    load_images(&docker, &version).map_err(|p| fail(shared, "images", p))?;
    step(shared, "images", StepState::Done, &format!("Version {version}"));

    // 5. .env — written once, then only the version line changes on an upgrade.
    step(shared, "config", StepState::Running, "Préparation des réglages…");
    let env_path = data.join(".env");
    let upgrading = write_env(&env_path, &version, &docker).map_err(|p| fail(shared, "config", p))?;
    let compose = resources_dir().join("docker-compose.prod.yml");
    let env = read_env(&env_path);
    let port: u16 = env.get("WINCHICKEN_PORT").and_then(|p| p.parse().ok()).unwrap_or(8080);
    step(shared, "config", StepState::Done, &format!("Port {port}"));

    // 6. Backup before an upgrade changes the database.
    let compose_args = |extra: &[&str]| -> Vec<String> {
        let mut args = vec!["compose".into(), "-p".into(), PROJECT.into(), "-f".into(), compose.to_string_lossy().into_owned(), "--env-file".into(), env_path.to_string_lossy().into_owned()];
        args.extend(extra.iter().map(|s| s.to_string()));
        args
    };
    if upgrading && stack_running(&docker, &refs(&compose_args(&["ps", "-q", "backup"]))) {
        step(shared, "backup", StepState::Running, "Sauvegarde de la base avant la mise à jour…");
        let out = docker::run(&docker, &refs(&compose_args(&["exec", "-T", "backup", "python", "manage.py", "backup_db"])));
        if !out.map(|o| o.status.success()).unwrap_or(false) {
            return Err(fail(shared, "backup", Problem::new(
                "backup_failed",
                "La sauvegarde avant mise à jour a échoué",
                "Par sécurité, la mise à jour n'a pas été appliquée : Winchicken reste dans sa version \
                 précédente. Cliquez sur Réessayer ; si cela recommence, copiez le rapport et envoyez-le au support.",
                &[RETRY],
            )));
        }
        step(shared, "backup", StepState::Done, "Sauvegarde faite");
    } else {
        step(shared, "backup", StepState::Skipped, "Pas de mise à jour");
    }

    // 7. Start (or update) the stack.
    step(shared, "start", StepState::Running, "Démarrage des services…");
    let out = docker::run(&docker, &refs(&compose_args(&["up", "-d", "--no-build", "--pull", "never", "--remove-orphans"])));
    if !out.as_ref().map(|o| o.status.success()).unwrap_or(false) {
        let stderr = out.map(|o| String::from_utf8_lossy(&o.stderr).to_string()).unwrap_or_default();
        let port_taken = stderr.contains("port is already allocated") || stderr.contains("address already in use");
        return Err(fail(shared, "start", if port_taken {
            Problem::new("port_taken", "Le port est déjà utilisé",
                &format!("Un autre programme utilise le port {port}. Fermez-le puis cliquez sur Réessayer, \
                          ou changez WINCHICKEN_PORT dans {} .", env_path.display()), &[RETRY])
        } else {
            Problem::new("start_failed", "Winchicken n'a pas pu démarrer",
                "Docker a refusé de démarrer les services. Cliquez sur Réessayer ; si cela recommence, \
                 redémarrez l'ordinateur, puis copiez le rapport (Détails techniques) pour le support.", &[RETRY])
        }));
    }
    step(shared, "start", StepState::Done, "Services démarrés");

    // 8. Wait until the app answers through nginx (migrations run on the first start).
    step(shared, "health", StepState::Running, "La première fois, cela peut prendre quelques minutes…");
    let started = Instant::now();
    loop {
        if platform::http_status(port, "/api/health/") == Some(200) {
            break;
        }
        if started.elapsed() > Duration::from_secs(420) {
            return Err(fail(shared, "health", Problem::new(
                "health_timeout",
                "Winchicken met trop de temps à démarrer",
                "L'ordinateur est peut-être très occupé. Fermez les autres programmes, attendez une minute, \
                 puis cliquez sur Réessayer.",
                &[RETRY],
            )));
        }
        step(shared, "health", StepState::Running, &format!("Préparation… ({} s)", started.elapsed().as_secs()));
        sleep(Duration::from_secs(3));
    }
    step(shared, "health", StepState::Done, "Prêt");

    let lan_urls = platform::lan_ip().map(|ip| vec![format!("http://{ip}:{port}")]).unwrap_or_default();
    shared.lock().unwrap().ready = Some(Ready { local_url: format!("http://localhost:{port}"), lan_urls });
    Ok(())
}

fn refs(v: &[String]) -> Vec<&str> {
    v.iter().map(String::as_str).collect()
}

fn stack_running(docker: &Path, args: &[&str]) -> bool {
    docker::run(docker, args).map(|o| o.status.success() && !o.stdout.is_empty()).unwrap_or(false)
}

/// Windows: Docker Desktop's VM takes up to half the RAM by default; on a 4 GB PC that starves
/// Windows. A .wslconfig that already exists is the user's and is left alone.
fn cap_wsl_memory() {
    if !cfg!(windows) {
        return;
    }
    let path = platform::home().join(".wslconfig");
    if path.exists() {
        crate::log(".wslconfig existe déjà : laissé tel quel");
        return;
    }
    let body = "# Écrit par Winchicken : limite la mémoire de Docker pour laisser de la place à Windows.\n[wsl2]\nmemory=2GB\n";
    match std::fs::write(&path, body) {
        Ok(()) => crate::log("~/.wslconfig écrit (memory=2GB)"),
        Err(e) => crate::log(&format!(".wslconfig non écrit : {e}")),
    }
}

fn image_list() -> Vec<String> {
    std::fs::read_to_string(resources_dir().join("images/images.txt"))
        .map(|t| t.lines().map(str::trim).filter(|l| !l.is_empty()).map(String::from).collect())
        .unwrap_or_default()
}

fn load_images(docker: &Path, version: &str) -> Result<(), Problem> {
    let images = image_list();
    let missing: Vec<&String> = images
        .iter()
        .filter(|tag| !docker::run(docker, &["image", "inspect", "--format", "{{.Id}}", tag]).map(|o| o.status.success()).unwrap_or(false))
        .collect();
    if images.is_empty() || (!missing.is_empty() && !resources_dir().join("images/winchicken-images.tar.gz").exists()) {
        return Err(Problem::new(
            "bundle_incomplete",
            "Fichiers d'installation incomplets",
            &format!("Les images de Winchicken {version} sont introuvables à côté du programme. Téléchargez \
                      de nouveau l'installateur depuis le site et relancez-le."),
            &[RETRY],
        ));
    }
    if missing.is_empty() {
        return Ok(());
    }
    crate::log(&format!("images manquantes : {missing:?}"));
    let archive = resources_dir().join("images/winchicken-images.tar.gz");
    let out = docker::run(docker, &["load", "-i", &archive.to_string_lossy()]);
    if out.map(|o| o.status.success()).unwrap_or(false) {
        Ok(())
    } else {
        Err(Problem::new(
            "images_load_failed",
            "Chargement de Winchicken impossible",
            "Docker n'a pas pu charger les fichiers de Winchicken. Vérifiez qu'il reste de la place sur \
             le disque, puis cliquez sur Réessayer.",
            &[RETRY],
        ))
    }
}

pub fn read_env(path: &Path) -> BTreeMap<String, String> {
    std::fs::read_to_string(path)
        .unwrap_or_default()
        .lines()
        .filter(|l| !l.trim_start().starts_with('#'))
        .filter_map(|l| l.split_once('='))
        .map(|(k, v)| (k.trim().to_string(), v.trim().to_string()))
        .collect()
}

/// First run: a fresh .env with random secrets, a free port and Web Push keys. Later runs only
/// move WINCHICKEN_VERSION — never the secrets: a new DB_PASSWORD would lock the app out of its
/// own database. Returns true when this is an upgrade.
pub fn write_env(path: &Path, version: &str, docker: &Path) -> Result<bool, Problem> {
    let io_err = |e: std::io::Error| Problem::new("env_write", "Réglages impossibles à enregistrer", &format!("{} : {e}", path.display()), &[RETRY]);
    if path.exists() {
        let text = std::fs::read_to_string(path).map_err(io_err)?;
        let current = read_env(path).get("WINCHICKEN_VERSION").cloned().unwrap_or_default();
        if current == version {
            return Ok(false);
        }
        let updated: Vec<String> = text
            .lines()
            .map(|l| if l.starts_with("WINCHICKEN_VERSION=") { format!("WINCHICKEN_VERSION={version}") } else { l.to_string() })
            .collect();
        std::fs::write(path, updated.join("\n") + "\n").map_err(io_err)?;
        crate::log(&format!("mise à jour {current} -> {version}"));
        return Ok(!current.is_empty());
    }
    let port = (8080..=8099).find(|p| platform::port_is_free(*p)).ok_or_else(|| Problem::new(
        "no_port",
        "Aucun port disponible",
        "Les ports 8080 à 8099 sont tous utilisés sur cet ordinateur. Fermez les autres logiciels serveur puis cliquez sur Réessayer.",
        &[RETRY],
    ))?;
    let (vapid_public, vapid_private) = vapid_keys(docker, version);
    let body = format!(
        "# Écrit une seule fois par l'installateur Winchicken. Ne pas partager (contient des mots de passe).\n\
         SECRET_KEY={}\nDB_PASSWORD={}\nWINCHICKEN_PORT={port}\nTZ=Africa/Douala\n\
         WINCHICKEN_IMAGE_PREFIX=winchicken\nWINCHICKEN_VERSION={version}\n\
         SMS_PROVIDER=console\nSMS_PROVIDER_API_KEY=\nSMS_PROVIDER_SENDER_ID=WINCHICKEN\n\
         VAPID_PUBLIC_KEY={vapid_public}\nVAPID_PRIVATE_KEY={vapid_private}\nVAPID_SUBJECT=mailto:admin@winchicken.local\n\
         BACKUP_INTERVAL_SECONDS=86400\nBACKUP_RETENTION_COUNT=7\n",
        platform::random_token(50),
        platform::random_token(32),
    );
    std::fs::write(path, body).map_err(io_err)?;
    // Secrets: readable by this account only. (On Windows the per-user app-data folder already is.)
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let _ = std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o600));
    }
    crate::log(&format!(".env créé ({})", path.display()));
    Ok(false)
}

/// Desktop notifications need a VAPID keypair; generated once with the app's own command in a
/// throwaway container. Blank keys just leave notifications off, never block the install.
fn vapid_keys(docker: &Path, version: &str) -> (String, String) {
    let image = format!("winchicken/backend:{version}");
    let out = docker::run(docker, &["run", "--rm", &image, "python", "manage.py", "generate_vapid_keys"]);
    let text = out.map(|o| String::from_utf8_lossy(&o.stdout).to_string()).unwrap_or_default();
    let get = |key: &str| text.lines().find_map(|l| l.strip_prefix(key)).unwrap_or("").trim().to_string();
    (get("VAPID_PUBLIC_KEY="), get("VAPID_PRIVATE_KEY="))
}

#[allow(dead_code)]
pub fn env_path() -> PathBuf {
    data_dir().join(".env")
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tmp(name: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!("wc-launcher-{name}-{}", std::process::id()));
        let _ = std::fs::create_dir_all(&dir);
        dir.join(".env")
    }

    #[test]
    fn upgrade_changes_only_the_version_line() {
        let path = tmp("upgrade");
        std::fs::write(&path, "SECRET_KEY=abc\nDB_PASSWORD=keep-me\nWINCHICKEN_VERSION=1.0.0\n# note\n").unwrap();
        let upgrading = write_env(&path, "1.1.0", Path::new("/nonexistent/docker")).unwrap();
        assert!(upgrading);
        let env = read_env(&path);
        assert_eq!(env["DB_PASSWORD"], "keep-me");
        assert_eq!(env["SECRET_KEY"], "abc");
        assert_eq!(env["WINCHICKEN_VERSION"], "1.1.0");
        assert!(std::fs::read_to_string(&path).unwrap().contains("# note"));
    }

    #[test]
    fn same_version_is_not_an_upgrade_and_rewrites_nothing() {
        let path = tmp("same");
        let body = "SECRET_KEY=abc\nWINCHICKEN_VERSION=1.0.0\n";
        std::fs::write(&path, body).unwrap();
        assert!(!write_env(&path, "1.0.0", Path::new("/nonexistent/docker")).unwrap());
        assert_eq!(std::fs::read_to_string(&path).unwrap(), body);
    }

    #[test]
    fn first_run_writes_random_secrets_and_a_port() {
        let path = tmp("fresh");
        let _ = std::fs::remove_file(&path);
        write_env(&path, "1.0.0", Path::new("/nonexistent/docker")).unwrap();
        let env = read_env(&path);
        assert_eq!(env["SECRET_KEY"].len(), 50);
        assert_eq!(env["DB_PASSWORD"].len(), 32);
        assert!(env["WINCHICKEN_PORT"].parse::<u16>().unwrap() >= 8080);
        assert_eq!(env["WINCHICKEN_VERSION"], "1.0.0");
        // A second fresh file must not reuse the same secrets.
        let other = tmp("fresh2");
        let _ = std::fs::remove_file(&other);
        write_env(&other, "1.0.0", Path::new("/nonexistent/docker")).unwrap();
        assert_ne!(read_env(&other)["SECRET_KEY"], env["SECRET_KEY"]);
    }
}
