//! What the setup page shows: the ordered steps, the current problem (if any) and the final
//! addresses. Shared between the worker thread and the local web server behind a Mutex; the
//! page polls `/status` once a second.

use serde_json::{json, Value};
use std::collections::VecDeque;
use std::sync::{Arc, Mutex};

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum StepState {
    Pending,
    Running,
    Done,
    Skipped,
    Failed,
}

impl StepState {
    fn as_str(self) -> &'static str {
        match self {
            StepState::Pending => "pending",
            StepState::Running => "running",
            StepState::Done => "done",
            StepState::Skipped => "skipped",
            StepState::Failed => "failed",
        }
    }
}

pub struct Step {
    pub id: &'static str,
    pub label: &'static str,
    pub state: StepState,
    pub detail: String,
}

/// A button offered under a problem. `id` is what the page POSTs to `/action/<id>`.
#[derive(Clone, Debug)]
pub struct Action {
    pub id: &'static str,
    pub label: &'static str,
}

/// A failure explained for the farm, never a stack trace: a title, what happened in plain
/// French, what to do next, and the buttons that do it. The raw log stays behind
/// "Détails techniques".
#[derive(Clone, Debug)]
pub struct Problem {
    pub code: &'static str,
    pub title: String,
    pub message: String,
    pub actions: Vec<Action>,
}

impl Problem {
    pub fn new(code: &'static str, title: &str, message: &str, actions: &[Action]) -> Self {
        Problem { code, title: title.into(), message: message.into(), actions: actions.to_vec() }
    }
}

pub const RETRY: Action = Action { id: "retry", label: "Réessayer" };
pub const INSTALL_DOCKER: Action = Action { id: "install_docker", label: "Installer Docker" };
pub const INSTALL_WSL: Action = Action { id: "install_wsl", label: "Installer WSL" };
#[allow(dead_code)] // Windows only
pub const REBOOT: Action = Action { id: "reboot", label: "Redémarrer l'ordinateur" };
#[allow(dead_code)] // Windows only
pub const CONTINUE: Action = Action { id: "retry", label: "Continuer sans redémarrer" };

pub struct Ready {
    pub local_url: String,
    pub lan_urls: Vec<String>,
}

pub struct Status {
    pub version: String,
    pub steps: Vec<Step>,
    pub problem: Option<Problem>,
    pub ready: Option<Ready>,
    /// (bytes done, bytes total) of the download in progress, if any.
    pub download: Option<(u64, u64)>,
    pub log: VecDeque<String>,
}

pub type Shared = Arc<Mutex<Status>>;

pub const STEPS: &[(&str, &str)] = &[
    ("check", "Vérification de l'ordinateur"),
    ("docker", "Docker installé"),
    ("docker_start", "Démarrage de Docker"),
    ("images", "Chargement de Winchicken"),
    ("config", "Configuration"),
    ("backup", "Sauvegarde avant mise à jour"),
    ("start", "Démarrage de Winchicken"),
    ("health", "Préparation de la base de données"),
];

impl Status {
    pub fn new(version: &str) -> Self {
        Status {
            version: version.into(),
            steps: STEPS
                .iter()
                .map(|(id, label)| Step { id, label, state: StepState::Pending, detail: String::new() })
                .collect(),
            problem: None,
            ready: None,
            download: None,
            log: VecDeque::new(),
        }
    }

    pub fn set(&mut self, id: &str, state: StepState, detail: &str) {
        if let Some(step) = self.steps.iter_mut().find(|s| s.id == id) {
            step.state = state;
            step.detail = detail.into();
        }
    }

    /// Everything back to pending before a retry, so a step that failed last time is not
    /// shown as failed while it is being run again.
    pub fn reset_steps(&mut self) {
        for step in &mut self.steps {
            step.state = StepState::Pending;
            step.detail.clear();
        }
        self.problem = None;
        self.download = None;
    }

    pub fn to_json(&self) -> Value {
        json!({
            "version": self.version,
            "steps": self.steps.iter().map(|s| json!({
                "id": s.id, "label": s.label, "state": s.state.as_str(), "detail": s.detail,
            })).collect::<Vec<_>>(),
            "problem": self.problem.as_ref().map(|p| json!({
                "code": p.code, "title": p.title, "message": p.message,
                "actions": p.actions.iter().map(|a| json!({"id": a.id, "label": a.label})).collect::<Vec<_>>(),
            })),
            "ready": self.ready.as_ref().map(|r| json!({"localUrl": r.local_url, "lanUrls": r.lan_urls})),
            "download": self.download.map(|(done, total)| json!({"done": done, "total": total})),
            "log": self.log.iter().collect::<Vec<_>>(),
        })
    }
}
