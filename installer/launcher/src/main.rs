//! Winchicken launcher: the program behind the desktop icon and the installer's last page.
//!
//! First run it installs everything (Docker if missing, the bundled images, a generated .env) and
//! starts Winchicken, showing each step on a page in the browser — no terminal, no command to
//! type. Afterwards it only makes sure Docker and Winchicken are running and opens the app.
//! Problems are shown in French with the next thing to do; the raw log sits behind
//! "Détails techniques".

#![cfg_attr(windows, windows_subsystem = "windows")]

mod docker;
mod platform;
mod setup;
mod state;

use state::{Shared, Status};
use std::io::Write;
use std::sync::mpsc::{channel, Receiver, Sender};
use std::sync::{Arc, Mutex, OnceLock};
use std::time::{Duration, Instant};
use tiny_http::{Header, Method, Response, Server};

const UI_PORT: u16 = 47823;
const INDEX_HTML: &str = include_str!("ui/index.html");

static LOG: OnceLock<Shared> = OnceLock::new();

/// Log to the page (last 200 lines) and to launcher.log in the data folder.
pub fn log(line: &str) {
    if let Some(shared) = LOG.get() {
        if let Ok(mut status) = shared.lock() {
            status.log.push_back(line.to_string());
            while status.log.len() > 200 {
                status.log.pop_front();
            }
        }
    }
    let path = platform::data_dir().join("launcher.log");
    if let Ok(mut file) = std::fs::OpenOptions::new().create(true).append(true).open(path) {
        let _ = writeln!(file, "{line}");
    }
}

fn main() {
    let _ = std::fs::create_dir_all(platform::data_dir());
    let version = setup::version();
    let ui_url = format!("http://127.0.0.1:{UI_PORT}/");

    // One launcher at a time. A second double-click opens Winchicken itself when it already
    // answers (the everyday case), otherwise the running launcher's setup page.
    let server = match Server::http(("127.0.0.1", UI_PORT)) {
        Ok(server) => server,
        Err(_) => {
            platform::open_url(&already_running(&version).unwrap_or(ui_url));
            return;
        }
    };

    let shared: Shared = Arc::new(Mutex::new(Status::new(&version)));
    let _ = LOG.set(shared.clone());
    log(&format!("--- Winchicken {version} — lancement ({:?})", std::env::args().skip(1).collect::<Vec<_>>()));

    // Everyday launch: already installed, same version, already answering → just open it.
    if let Some(url) = already_running(&version) {
        log(&format!("déjà en marche : {url}"));
        platform::open_url(&url);
        return;
    }

    let (tx, rx) = channel::<String>();
    {
        let shared = shared.clone();
        std::thread::spawn(move || worker(shared, rx));
    }
    platform::open_url(&ui_url);
    serve(server, shared, tx);
}

fn already_running(version: &str) -> Option<String> {
    let env = setup::read_env(&platform::data_dir().join(".env"));
    if env.get("WINCHICKEN_VERSION").map(String::as_str) != Some(version) {
        return None;
    }
    let port: u16 = env.get("WINCHICKEN_PORT")?.parse().ok()?;
    (platform::http_status(port, "/api/health/") == Some(200)).then(|| format!("http://localhost:{port}"))
}

/// Runs setup; on a problem, waits for the button the user presses and acts on it.
fn worker(shared: Shared, actions: Receiver<String>) {
    let mut next = String::from("retry");
    loop {
        shared.lock().unwrap().reset_steps();
        let result = match next.as_str() {
            "install_docker" => docker::install(&shared).and_then(|_| setup::run(&shared)),
            "install_wsl" => docker::install_wsl().and_then(|_| setup::run(&shared)),
            "reboot" => {
                platform::register_resume_after_reboot();
                platform::reboot();
                log("redémarrage demandé");
                return;
            }
            _ => setup::run(&shared),
        };
        match result {
            Ok(()) => {
                log("Winchicken est prêt");
                return;
            }
            Err(problem) => {
                log(&format!("problème : {} — {}", problem.code, problem.title));
                shared.lock().unwrap().problem = Some(problem);
                match actions.recv() {
                    Ok(action) => next = action,
                    Err(_) => return,
                }
            }
        }
    }
}

/// The setup page and its small API, on 127.0.0.1 only. Stops 15 minutes after Winchicken is
/// ready (the page has redirected by then), or when the page asks it to.
fn serve(server: Server, shared: Shared, actions: Sender<String>) {
    let mut ready_since: Option<Instant> = None;
    loop {
        if shared.lock().unwrap().ready.is_some() {
            let since = *ready_since.get_or_insert_with(Instant::now);
            if since.elapsed() > Duration::from_secs(15 * 60) {
                return;
            }
        }
        let Ok(Some(mut request)) = server.recv_timeout(Duration::from_secs(1)) else { continue };
        let url = request.url().to_string();
        let (path, query) = url.split_once('?').unwrap_or((&url, ""));
        let response = match (request.method(), path) {
            (Method::Get, "/") => Response::from_string(INDEX_HTML).with_header(header("Content-Type", "text/html; charset=utf-8")),
            (Method::Get, "/status") => {
                let body = shared.lock().unwrap().to_json().to_string();
                Response::from_string(body).with_header(header("Content-Type", "application/json")).with_header(header("Cache-Control", "no-store"))
            }
            (Method::Get, "/qr.svg") => {
                let text = query.strip_prefix("text=").map(percent_decode).unwrap_or_default();
                Response::from_string(qr_svg(&text)).with_header(header("Content-Type", "image/svg+xml"))
            }
            (Method::Post, p) if p.starts_with("/action/") => {
                let action = p.trim_start_matches("/action/").to_string();
                let mut body = String::new();
                let _ = request.as_reader().read_to_string(&mut body);
                if action == "quit" {
                    let _ = request.respond(Response::from_string("ok"));
                    return;
                }
                let waiting = shared.lock().unwrap().problem.take().is_some();
                if waiting {
                    let _ = actions.send(action);
                }
                Response::from_string("ok")
            }
            _ => Response::from_string("introuvable").with_status_code(404),
        };
        let _ = request.respond(response);
    }
}

fn header(name: &str, value: &str) -> Header {
    Header::from_bytes(name.as_bytes(), value.as_bytes()).expect("en-tête valide")
}

fn percent_decode(s: &str) -> String {
    let bytes = s.as_bytes();
    let mut out = Vec::with_capacity(bytes.len());
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'%' && i + 2 < bytes.len() {
            if let Ok(v) = u8::from_str_radix(&s[i + 1..i + 3], 16) {
                out.push(v);
                i += 3;
                continue;
            }
        }
        out.push(if bytes[i] == b'+' { b' ' } else { bytes[i] });
        i += 1;
    }
    String::from_utf8_lossy(&out).into_owned()
}

fn qr_svg(text: &str) -> String {
    match qrcode::QrCode::new(text.as_bytes()) {
        Ok(code) => code.render::<qrcode::render::svg::Color>().min_dimensions(200, 200).quiet_zone(true).build(),
        Err(_) => String::from("<svg xmlns='http://www.w3.org/2000/svg'/>"),
    }
}

