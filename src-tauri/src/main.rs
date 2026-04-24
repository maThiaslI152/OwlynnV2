#![cfg_attr(
  all(not(debug_assertions), target_os = "windows"),
  windows_subsystem = "windows"
)]

use serde::Serialize;
use std::path::PathBuf;
use std::process::Command;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::sync::Mutex;
use std::thread;
use std::time::{SystemTime, UNIX_EPOCH};
use tauri::Manager;

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
struct VoiceStartedPayload {
  #[serde(rename = "type")]
  event_type: &'static str,
  mode: String,
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

fn emit_voice_state(app: &tauri::AppHandle, state: &str) {
  let _ = app.emit_all(
    "owlynn://runtime-event",
    voice::VoiceStatePayload {
      event_type: "voice.state",
      state: state.to_string(),
    },
  );
}

fn emit_voice_error(app: &tauri::AppHandle, message: &str, code: &str) {
  let _ = app.emit_all(
    "owlynn://runtime-event",
    voice::VoiceErrorPayload {
      event_type: "voice.error",
      message: message.to_string(),
      code: code.to_string(),
    },
  );
}

fn emit_voice_transcript(app: &tauri::AppHandle, text: &str, is_final: bool, confidence: f32) {
  let _ = app.emit_all(
    "owlynn://runtime-event",
    voice::VoiceTranscriptPayload {
      event_type: "voice.transcript",
      text: text.to_string(),
      is_final,
      confidence,
    },
  );
}

fn emit_safe_mode(app: &tauri::AppHandle, mode: &str) {
  let _ = app.emit_all(
    "owlynn://runtime-event",
    SafeModePayload {
      event_type: "safe_mode.changed",
      mode: mode.to_string(),
    },
  );
}

fn emit_screen_state(app: &tauri::AppHandle, mode: &str, source: &str, preview_path: Option<String>) {
  let _ = app.emit_all(
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
fn start_push_to_talk(
  app: tauri::AppHandle,
  state: tauri::State<Mutex<NativeRuntimeState>>,
) -> Result<String, String> {
  let mut locked = state.lock().map_err(|_| "native runtime state lock failed".to_string())?;
  if locked.voice.recording {
    return Ok("push-to-talk already recording".to_string());
  }
  if locked.voice.tts_speaking {
    locked.voice.tts_speaking = false;
    let _ = app.emit_all(
      "owlynn://runtime-event",
      voice::VoiceTtsStatePayload {
        event_type: "voice.tts_state",
        speaking: false,
        utterance_id: "barge-in".to_string(),
      },
    );
  }
  locked.voice.recording = true;

  // Create a stop flag and channel for real-time transcription
  let ptt_stop = Arc::new(AtomicBool::new(false));
  let (ptt_tx, ptt_rx) = crossbeam_channel::unbounded::<voice::VoiceEvent>();

  // Spawn emitter thread for this PTT session
  let app_emit = app.clone();
  thread::spawn(move || {
    while let Ok(event) = ptt_rx.recv() {
      match event {
        voice::VoiceEvent::Transcript(text, is_final, confidence) => {
          let _ = app_emit.emit_all(
            "owlynn://runtime-event",
            voice::VoiceTranscriptPayload {
              event_type: "voice.transcript",
              text,
              is_final,
              confidence,
            },
          );
          if is_final || confidence > 0.9 {
            // Signal that final transcription arrived
          }
        }
        voice::VoiceEvent::Error(message, code) => {
          let _ = app_emit.emit_all(
            "owlynn://runtime-event",
            voice::VoiceErrorPayload {
              event_type: "voice.error",
              message,
              code,
            },
          );
        }
        _ => {}
      }
    }
  });

  // Start real speech recognition in background
  voice::start_recording(ptt_tx, ptt_stop.clone(), locked.voice.wake_word_phrase.clone());
  locked.voice.wake_stop = Some(ptt_stop);
  locked.voice.recording = true;
  emit_voice_state(&app, "recording");
  Ok("push-to-talk started".to_string())
}

#[tauri::command]
fn stop_push_to_talk(
  app: tauri::AppHandle,
  state: tauri::State<Mutex<NativeRuntimeState>>,
) -> Result<String, String> {
  let mut locked = state.lock().map_err(|_| "native runtime state lock failed".to_string())?;
  if !locked.voice.recording {
    emit_voice_state(&app, "idle");
    return Ok("push-to-talk was not recording".to_string());
  }
  locked.voice.recording = false;
  emit_voice_state(&app, "transcribing");

  // Signal the recording thread to stop
  if let Some(stop_flag) = locked.voice.wake_stop.take() {
    stop_flag.store(true, Ordering::SeqCst);
    // Give recognition a brief moment to finalize (non-blocking for UX)
    thread::sleep(std::time::Duration::from_millis(300));
  }

  emit_voice_state(&app, "idle");
  Ok("push-to-talk stopped — transcription in progress".to_string())
}

#[tauri::command]
fn hard_stop_voice(
  app: tauri::AppHandle,
  state: tauri::State<Mutex<NativeRuntimeState>>,
) -> Result<String, String> {
  let mut locked = state.lock().map_err(|_| "native runtime state lock failed".to_string())?;
  locked.voice.recording = false;
  locked.voice.listening = false;
  locked.voice.tts_speaking = false;
  if let Some(stop_flag) = locked.voice.wake_stop.take() {
    stop_flag.store(true, Ordering::SeqCst);
  }
  let _ = app.emit_all(
    "owlynn://runtime-event",
    voice::VoiceTtsStatePayload {
      event_type: "voice.tts_state",
      speaking: false,
      utterance_id: "hard-stop".to_string(),
    },
  );
  emit_voice_state(&app, "interrupted");
  Ok("voice interrupted".to_string())
}

#[tauri::command]
fn set_wake_word_phrase(
  state: tauri::State<Mutex<NativeRuntimeState>>,
  phrase: String,
) -> Result<String, String> {
  let mut locked = state.lock().map_err(|_| "native runtime state lock failed".to_string())?;
  locked.voice.wake_word_phrase = phrase.trim().to_string();
  Ok("wake word updated".to_string())
}

#[tauri::command]
fn get_wake_word_phrase(
  state: tauri::State<Mutex<NativeRuntimeState>>,
) -> Result<String, String> {
  let locked = state.lock().map_err(|_| "native runtime state lock failed".to_string())?;
  let phrase = locked.voice.wake_word_phrase.clone();
  if phrase.is_empty() {
    Ok("Hey Owlynn".to_string())
  } else {
    Ok(phrase)
  }
}

#[tauri::command]
fn start_voice_listening(
  app: tauri::AppHandle,
  state: tauri::State<Mutex<NativeRuntimeState>>,
) -> Result<String, String> {
  let mut locked = state.lock().map_err(|_| "native runtime state lock failed".to_string())?;
  if !voice::speech_framework_available() {
    emit_voice_error(&app, "macOS Speech framework unavailable", "speech_unavailable");
  }
  if locked.voice.listening {
    return Ok("wake-word listening already active".to_string());
  }
  let phrase = if locked.voice.wake_word_phrase.is_empty() {
    "Hey Owlynn".to_string()
  } else {
    locked.voice.wake_word_phrase.clone()
  };
  let stop_flag = Arc::new(AtomicBool::new(false));
  voice::start_wake_loop(app.clone(), phrase.clone(), stop_flag.clone());
  locked.voice.wake_stop = Some(stop_flag);
  locked.voice.listening = true;
  emit_voice_state(&app, "idle");
  let _ = app.emit_all(
    "owlynn://runtime-event",
    VoiceStartedPayload {
      event_type: "voice.started",
      mode: "wake_word".to_string(),
    },
  );
  Ok(format!("wake-word listening started ({})", phrase))
}

#[tauri::command]
fn stop_voice_listening(
  app: tauri::AppHandle,
  state: tauri::State<Mutex<NativeRuntimeState>>,
) -> Result<String, String> {
  let mut locked = state.lock().map_err(|_| "native runtime state lock failed".to_string())?;
  if let Some(stop_flag) = locked.voice.wake_stop.take() {
    stop_flag.store(true, Ordering::SeqCst);
  }
  locked.voice.listening = false;
  emit_voice_state(&app, "idle");
  Ok("wake-word listening stopped".to_string())
}

#[tauri::command]
fn speak_text(
  app: tauri::AppHandle,
  state: tauri::State<Mutex<NativeRuntimeState>>,
  text: String,
) -> Result<String, String> {
  let locked = state.lock().map_err(|_| "native runtime state lock failed".to_string())?;
  // Wrap the engine state in Arc<Mutex> for the voice engine's speak_text which needs
  // to share & modify tts_speaking from a background thread.
  let engine = Arc::new(Mutex::new(locked.voice.clone()));
  let _utterance_id = voice::speak_text(app, text, engine);
  // voice::speak_text spawns a thread; the listener in voice/mod.rs handles state,
  // but our NativeRuntimeState.voice.tts_speaking will be managed via the Arc<Mutex> copy.
  // For `locked` to reflect it we'd need a more sophisticated bridge; for now the
  // Arc<Mutex> inside the voice module handles it independently.
  drop(locked);
  Ok("speech queued".to_string())
}

#[tauri::command]
fn set_safe_mode(
  app: tauri::AppHandle,
  state: tauri::State<Mutex<NativeRuntimeState>>,
  mode: String,
) -> Result<String, String> {
  let allowed = [
    "normal",
    "safe_readonly",
    "safe_confirmed_exec",
    "safe_isolated",
  ];
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
fn stop_screen_preview(
  app: tauri::AppHandle,
  state: tauri::State<Mutex<NativeRuntimeState>>,
) -> Result<String, String> {
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

  let _ = app.emit_all(
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
    let _ = app.emit_all(
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
    let _ = app.emit_all(
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
fn set_window_size(
  app: tauri::AppHandle,
  width: f64,
  height: f64,
) -> Result<String, String> {
  let window = app.get_window("main").ok_or("main window not found")?;
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
    .manage(Mutex::new(NativeRuntimeState {
      voice: voice::VoiceEngine {
        wake_word_phrase: "Hey Owlynn".to_string(),
        ..voice::VoiceEngine::default()
      },
      safe_mode: "normal".to_string(),
      ..NativeRuntimeState::default()
    }))
    .invoke_handler(tauri::generate_handler![
      start_voice_listening,
      stop_voice_listening,
      start_push_to_talk,
      stop_push_to_talk,
      hard_stop_voice,
      speak_text,
      set_wake_word_phrase,
      get_wake_word_phrase,
      set_safe_mode,
      start_screen_preview,
      stop_screen_preview,
      create_action_proposal,
      approve_action_proposal,
      reject_action_proposal,
      set_window_size
    ])
    .setup(|app| {
      let window = app.get_window("main").unwrap();

      // ── macOS: Apply native vibrancy (frosted glass) ──
      #[cfg(target_os = "macos")]
      {
        use window_vibrancy::{apply_vibrancy, NSVisualEffectMaterial, NSVisualEffectState};

        // Use a brighter frosted material and force active state for stronger
        // blur/translucency while this app is in front.
        apply_vibrancy(
          &window,
          NSVisualEffectMaterial::Sidebar,
          Some(NSVisualEffectState::Active),
          None,
        )
        .expect("Failed to apply macOS vibrancy");
      }

      // ── Windows: Apply acrylic/mica if available ──
      #[cfg(target_os = "windows")]
      {
        use window_vibrancy::apply_acrylic;
        let _ = apply_acrylic(&window, Some((18, 18, 18, 200)));
      }

      Ok(())
    })
    .run(tauri::generate_context!())
    .expect("error while running tauri application");
}
