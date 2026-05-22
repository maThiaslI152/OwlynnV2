#![cfg_attr(all(not(debug_assertions), target_os = "windows"), windows_subsystem = "windows")]

use serde::Serialize;
use std::path::PathBuf;
use std::process::Command;
use std::sync::{Arc, Mutex};
use std::time::{SystemTime, UNIX_EPOCH};
use tauri::{Emitter, Manager};

mod voice;

#[derive(Default)]
struct NativeRuntimeState {
  voice: voice::VoiceEngine,
  safe_mode: String,
  screen_preview_active: bool,
  last_preview_path: Option<String>,
  proposals: Vec<ActionProposal>,
}

#[derive(Clone, Serialize)]
struct SafeModePayload {
  #[serde(rename = "type")]
  event_type: &'static str,
  mode: String,
}

#[derive(Clone, Serialize)]
struct ScreenAssistPayload {
  #[serde(rename = "type")]
  event_type: &'static str,
  mode: String,
  source: String,
  preview_path: Option<String>,
}

#[derive(Serialize, Clone)]
struct ActionProposal {
  id: String,
  summary: String,
  source: String,
  created_at: u128,
  status: String,
}

#[derive(Clone, Serialize)]
struct ActionProposalPayload {
  #[serde(rename = "type")]
  event_type: &'static str,
  proposal: ActionProposal,
}

#[derive(Clone, Serialize)]
struct ActionProposalResultPayload {
  #[serde(rename = "type")]
  event_type: &'static str,
  id: String,
  status: String,
}

fn emit_safe_mode(app: &tauri::AppHandle, mode: &str) {
  let _ = app.emit(
    "owlynn://runtime-event",
    SafeModePayload {
      event_type: "safe_mode.changed",
      mode: mode.to_string(),
    },
  );
}

fn emit_screen_state(app: &tauri::AppHandle, mode: &str, source: &str, preview_path: Option<String>) {
  let _ = app.emit(
    "owlynn://runtime-event",
    ScreenAssistPayload {
      event_type: "screen_assist.state",
      mode: mode.to_string(),
      source: source.to_string(),
      preview_path,
    },
  );
}

fn make_preview_path(source: &str) -> PathBuf {
  let millis = SystemTime::now()
    .duration_since(UNIX_EPOCH)
    .map(|d| d.as_millis())
    .unwrap_or(0);
  let file_name = format!("owlynn-preview-{}-{}.jpg", source, millis);
  std::env::temp_dir().join(file_name)
}

fn now_millis() -> u128 {
  SystemTime::now()
    .duration_since(UNIX_EPOCH)
    .map(|d| d.as_millis())
    .unwrap_or(0)
}

#[tauri::command]
fn speak_text(app: tauri::AppHandle, state: tauri::State<Mutex<NativeRuntimeState>>, text: String) -> Result<String, String> {
  const MAX_TTS_LENGTH: usize = 5000;
  if text.len() > MAX_TTS_LENGTH {
    return Err(format!("text too long ({} chars, max {})", text.len(), MAX_TTS_LENGTH));
  }
  if text.trim().is_empty() {
    return Err("text must not be empty".to_string());
  }
  let locked = state.lock().map_err(|_| "native runtime state lock failed".to_string())?;
  let engine = Arc::new(Mutex::new(locked.voice.clone()));
  let _ = voice::speak_text(app, text, engine);
  Ok("speech queued".to_string())
}

#[tauri::command]
fn set_safe_mode(app: tauri::AppHandle, state: tauri::State<Mutex<NativeRuntimeState>>, mode: String) -> Result<String, String> {
  let allowed = ["normal", "safe_readonly", "safe_confirmed_exec", "safe_isolated"];
  if !allowed.contains(&mode.as_str()) {
    return Err(format!("invalid safe mode '{}'", mode));
  }
  let mut locked = state.lock().map_err(|_| "native runtime state lock failed".to_string())?;
  locked.safe_mode = mode.clone();
  emit_safe_mode(&app, &mode);
  Ok(format!("safe mode set: {}", mode))
}

#[tauri::command]
fn start_screen_preview(
  app: tauri::AppHandle,
  state: tauri::State<Mutex<NativeRuntimeState>>,
  source: String,
) -> Result<String, String> {
  let allowed = ["screen", "window", "region"];
  if !allowed.contains(&source.as_str()) {
    return Err(format!("invalid screen source '{}'", source));
  }
  let preview_path = make_preview_path(&source);
  #[cfg(target_os = "macos")]
  {
    let status = Command::new("screencapture")
      .arg("-x")
      .arg("-t")
      .arg("jpg")
      .arg(&preview_path)
      .status()
      .map_err(|err| format!("failed to execute screencapture: {}", err))?;
    if !status.success() {
      return Err("screencapture failed".to_string());
    }
  }
  let path_string = preview_path.to_string_lossy().to_string();
  let mut locked = state.lock().map_err(|_| "native runtime state lock failed".to_string())?;
  locked.screen_preview_active = true;
  locked.last_preview_path = Some(path_string.clone());
  emit_screen_state(&app, "preview", &source, Some(path_string.clone()));
  Ok(format!("screen preview started: {} ({})", source, path_string))
}

#[tauri::command]
fn stop_screen_preview(app: tauri::AppHandle, state: tauri::State<Mutex<NativeRuntimeState>>) -> Result<String, String> {
  let mut locked = state.lock().map_err(|_| "native runtime state lock failed".to_string())?;
  locked.screen_preview_active = false;
  emit_screen_state(&app, "off", "screen", locked.last_preview_path.clone());
  Ok("screen preview stopped".to_string())
}

#[tauri::command]
fn create_action_proposal(
  app: tauri::AppHandle,
  state: tauri::State<Mutex<NativeRuntimeState>>,
  summary: String,
) -> Result<ActionProposal, String> {
  let proposal = ActionProposal {
    id: format!("proposal-{}", now_millis()),
    summary,
    source: "screen_assist".to_string(),
    created_at: now_millis(),
    status: "pending".to_string(),
  };
  {
    let mut locked = state.lock().map_err(|_| "native runtime state lock failed".to_string())?;
    locked.proposals.push(proposal.clone());
  }
  let _ = app.emit(
    "owlynn://runtime-event",
    ActionProposalPayload {
      event_type: "action.proposal",
      proposal: proposal.clone(),
    },
  );
  Ok(proposal)
}

#[tauri::command]
fn approve_action_proposal(
  app: tauri::AppHandle,
  state: tauri::State<Mutex<NativeRuntimeState>>,
  id: String,
) -> Result<String, String> {
  let mut locked = state.lock().map_err(|_| "native runtime state lock failed".to_string())?;
  if let Some(p) = locked.proposals.iter_mut().find(|p| p.id == id) {
    p.status = "approved".to_string();
    let _ = app.emit(
      "owlynn://runtime-event",
      ActionProposalResultPayload {
        event_type: "action.proposal.result",
        id: p.id.clone(),
        status: p.status.clone(),
      },
    );
    return Ok(format!("proposal approved: {}", p.id));
  }
  Err(format!("proposal not found: {}", id))
}

#[tauri::command]
fn reject_action_proposal(
  app: tauri::AppHandle,
  state: tauri::State<Mutex<NativeRuntimeState>>,
  id: String,
) -> Result<String, String> {
  let mut locked = state.lock().map_err(|_| "native runtime state lock failed".to_string())?;
  if let Some(p) = locked.proposals.iter_mut().find(|p| p.id == id) {
    p.status = "rejected".to_string();
    let _ = app.emit(
      "owlynn://runtime-event",
      ActionProposalResultPayload {
        event_type: "action.proposal.result",
        id: p.id.clone(),
        status: p.status.clone(),
      },
    );
    return Ok(format!("proposal rejected: {}", p.id));
  }
  Err(format!("proposal not found: {}", id))
}

#[tauri::command]
fn set_window_size(app: tauri::AppHandle, width: f64, height: f64) -> Result<String, String> {
  let window = app.get_webview_window("main").ok_or("main window not found")?;
  window
    .set_size(tauri::Size::Physical(tauri::PhysicalSize {
      width: width as u32,
      height: height as u32,
    }))
    .map_err(|e| format!("set_size failed: {}", e))?;
  Ok(format!("window resized to {}x{}", width, height))
}

fn main() {
  tauri::Builder::default()
    .plugin(tauri_plugin_shell::init())
    .plugin(tauri_plugin_opener::init())
    .manage(Mutex::new(NativeRuntimeState {
      voice: voice::VoiceEngine {
        wake_word_phrase: "Athena".to_string(),
        ..voice::VoiceEngine::default()
      },
      safe_mode: "normal".to_string(),
      ..NativeRuntimeState::default()
    }))
    .invoke_handler(tauri::generate_handler![
      speak_text,
      set_safe_mode,
      start_screen_preview,
      stop_screen_preview,
      create_action_proposal,
      approve_action_proposal,
      reject_action_proposal,
      set_window_size
    ])
    .setup(|app| {
      #[cfg(target_os = "macos")]
      {
        let window = app.get_webview_window("main").ok_or("main window not found")?;
        use cocoa::appkit::{NSColor, NSWindow};
        use cocoa::base::{id, nil};
        let ns_window = window.ns_window().unwrap() as id;
        unsafe {
          let bg_color = NSColor::colorWithRed_green_blue_alpha_(
            nil,
            14.0 / 255.0,
            28.0 / 255.0,
            49.0 / 255.0,
            1.0,
          );
          ns_window.setBackgroundColor_(bg_color);
        }
      }
      Ok(())
    })
    .run(tauri::generate_context!())
    .expect("error while running tauri application");
}
