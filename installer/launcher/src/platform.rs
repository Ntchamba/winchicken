//! Operating-system differences in one place: where data lives, how a command is run without a
//! console window flashing up, how the browser is opened, and the few machine facts setup needs.

use std::io::{Read, Write};
use std::net::{SocketAddr, TcpListener, TcpStream, UdpSocket};
use std::path::PathBuf;
use std::process::Command;
use std::time::Duration;

/// Where .env, the log and downloads live. Kept outside the install folder so a reinstall or an
/// upgrade never touches it. `WINCHICKEN_DATA_DIR` overrides it (tests).
pub fn data_dir() -> PathBuf {
    if let Ok(dir) = std::env::var("WINCHICKEN_DATA_DIR") {
        return PathBuf::from(dir);
    }
    if cfg!(windows) {
        let base = std::env::var("LOCALAPPDATA").unwrap_or_else(|_| ".".into());
        PathBuf::from(base).join("Winchicken")
    } else if cfg!(target_os = "macos") {
        home().join("Library/Application Support/Winchicken")
    } else {
        home().join(".local/share/winchicken")
    }
}

/// The files shipped with the installer (compose file, images, VERSION). Next to the executable
/// on Windows/Linux, in Contents/Resources on macOS. `WINCHICKEN_RESOURCES_DIR` overrides it.
pub fn resources_dir() -> PathBuf {
    if let Ok(dir) = std::env::var("WINCHICKEN_RESOURCES_DIR") {
        return PathBuf::from(dir);
    }
    let exe = std::env::current_exe().unwrap_or_default();
    let dir = exe.parent().map(PathBuf::from).unwrap_or_default();
    if cfg!(target_os = "macos") {
        let bundled = dir.join("../Resources");
        if bundled.exists() {
            return bundled;
        }
    }
    dir.join("resources")
}

pub fn home() -> PathBuf {
    std::env::var("HOME").or_else(|_| std::env::var("USERPROFILE")).map(PathBuf::from).unwrap_or_default()
}

/// A command that never opens a console window on Windows (the launcher itself has none).
pub fn command(program: impl AsRef<std::ffi::OsStr>) -> Command {
    #[allow(unused_mut)]
    let mut cmd = Command::new(program);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }
    cmd
}

pub fn open_url(url: &str) {
    // Tests drive the page with their own (headless) browser instead.
    if std::env::var_os("WINCHICKEN_NO_BROWSER").is_some() {
        crate::log(&format!("(navigateur non ouvert) {url}"));
        return;
    }
    let result = if cfg!(windows) {
        // `explorer <url>` hands it to the default browser without a console.
        command("explorer").arg(url).spawn()
    } else if cfg!(target_os = "macos") {
        command("open").arg(url).spawn()
    } else {
        command("xdg-open").arg(url).spawn()
    };
    if let Err(err) = result {
        crate::log(&format!("impossible d'ouvrir le navigateur: {err}"));
    }
}

/// URL-safe random string for SECRET_KEY / DB_PASSWORD.
pub fn random_token(len: usize) -> String {
    const ALPHABET: &[u8] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";
    let mut bytes = vec![0u8; len];
    getrandom::getrandom(&mut bytes).expect("générateur aléatoire du système indisponible");
    bytes.iter().map(|b| ALPHABET[(*b as usize) % ALPHABET.len()] as char).collect()
}

/// Free space, in bytes, on the disk holding `path` — `None` when it cannot be read, which is
/// treated as "do not block the install on it".
pub fn free_disk_bytes(path: &std::path::Path) -> Option<u64> {
    if cfg!(windows) {
        let drive = path.to_string_lossy().chars().next().unwrap_or('C');
        let out = command("powershell")
            .args(["-NoProfile", "-Command", &format!("(Get-PSDrive -Name {drive}).Free")])
            .output()
            .ok()?;
        String::from_utf8_lossy(&out.stdout).trim().parse().ok()
    } else {
        let out = command("df").args(["-Pk"]).arg(path).output().ok()?;
        let text = String::from_utf8_lossy(&out.stdout);
        let line = text.lines().nth(1)?;
        let kb: u64 = line.split_whitespace().nth(3)?.parse().ok()?;
        Some(kb * 1024)
    }
}

/// Total RAM in bytes, for a warning only (4 GB works, slowly).
pub fn total_ram_bytes() -> Option<u64> {
    if cfg!(windows) {
        let out = command("powershell")
            .args(["-NoProfile", "-Command", "(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory"])
            .output()
            .ok()?;
        String::from_utf8_lossy(&out.stdout).trim().parse().ok()
    } else if cfg!(target_os = "macos") {
        let out = command("sysctl").args(["-n", "hw.memsize"]).output().ok()?;
        String::from_utf8_lossy(&out.stdout).trim().parse().ok()
    } else {
        let text = std::fs::read_to_string("/proc/meminfo").ok()?;
        let kb: u64 = text.lines().find(|l| l.starts_with("MemTotal"))?.split_whitespace().nth(1)?.parse().ok()?;
        Some(kb * 1024)
    }
}

/// The PC's address on the farm network. Connecting a UDP socket sends nothing; it only makes
/// the OS pick the interface it would route through, which is the one phones can reach.
pub fn lan_ip() -> Option<String> {
    let socket = UdpSocket::bind("0.0.0.0:0").ok()?;
    socket.connect("192.168.1.1:9").or_else(|_| socket.connect("10.0.0.1:9")).ok()?;
    let ip = socket.local_addr().ok()?.ip();
    if ip.is_loopback() || ip.is_unspecified() {
        None
    } else {
        Some(ip.to_string())
    }
}

/// Whether Docker will be able to publish `port`. Binding the wildcard address alone misses
/// programs listening on loopback only: Windows lets a wildcard bind coexist with a listener on
/// 127.0.0.1, macOS does too because Rust sets SO_REUSEADDR, and nothing IPv4 sees a listener
/// on [::1] (a local dev server bound to "localhost"). Docker's publish then fails, or the
/// browser's "localhost" reaches the other program. So also knock on both loopbacks.
pub fn port_is_free(port: u16) -> bool {
    if TcpListener::bind(("0.0.0.0", port)).is_err() {
        return false;
    }
    let knock = Duration::from_millis(300);
    let loopbacks: [SocketAddr; 2] = [([127, 0, 0, 1], port).into(), (std::net::Ipv6Addr::LOCALHOST, port).into()];
    loopbacks.iter().all(|addr| TcpStream::connect_timeout(addr, knock).is_err())
}

/// Minimal HTTP GET returning the status code — enough to poll /api/health/ without a client
/// library.
pub fn http_status(port: u16, path: &str) -> Option<u16> {
    let addr: SocketAddr = format!("127.0.0.1:{port}").parse().ok()?;
    let mut stream = TcpStream::connect_timeout(&addr, Duration::from_secs(3)).ok()?;
    stream.set_read_timeout(Some(Duration::from_secs(10))).ok()?;
    write!(stream, "GET {path} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n").ok()?;
    let mut head = [0u8; 64];
    let n = stream.read(&mut head).ok()?;
    let text = String::from_utf8_lossy(&head[..n]);
    text.split_whitespace().nth(1)?.parse().ok()
}

/// Windows: run this launcher again once, at the next log-in (after the reboot Docker asks for).
pub fn register_resume_after_reboot() {
    #[cfg(windows)]
    {
        let exe = std::env::current_exe().unwrap_or_default();
        let value = format!("\"{}\" --resume", exe.display());
        let _ = command("reg")
            .args(["add", r"HKCU\Software\Microsoft\Windows\CurrentVersion\RunOnce", "/v", "Winchicken", "/d", &value, "/f"])
            .output();
    }
}

pub fn reboot() {
    if cfg!(windows) {
        let _ = command("shutdown").args(["/r", "/t", "10", "/c", "Redémarrage pour terminer l'installation de Docker (Winchicken)"]).spawn();
    }
}
