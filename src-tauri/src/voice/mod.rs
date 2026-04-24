use serde::Serialize;
use std::io::{BufRead, BufReader, Write};
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;
use tauri::{AppHandle, Emitter, Manager};

#[derive(Default, Clone)]
pub struct VoiceEngineState {
  pub listening: bool,
  pub tts_speaking: bool,
  pub wake_word_phrase: String,
  pub wake_stop: Option<Arc<AtomicBool>>,
}

pub type VoiceEngine = VoiceEngineState;

#[derive(Clone, Serialize)]
pub struct VoiceStatePayload {
  #[serde(rename = "type")]
  pub event_type: &'static str,
  pub state: String,
}

#[derive(Clone, Serialize)]
pub struct VoiceTranscriptPayload {
  #[serde(rename = "type")]
  pub event_type: &'static str,
  pub text: String,
  pub is_final: bool,
  pub confidence: f32,
}

#[derive(Clone, Serialize)]
pub struct VoiceWakeWordPayload {
  #[serde(rename = "type")]
  pub event_type: &'static str,
  pub phrase: String,
  pub confidence: f32,
}

#[derive(Clone, Serialize)]
pub struct VoiceErrorPayload {
  #[serde(rename = "type")]
  pub event_type: &'static str,
  pub message: String,
  pub code: String,
}

#[derive(Clone, Serialize)]
pub struct VoiceTtsStatePayload {
  #[serde(rename = "type")]
  pub event_type: &'static str,
  pub speaking: bool,
  pub utterance_id: String,
}

#[derive(Debug)]
pub enum VoiceEvent {
  Transcript(String, bool, f32),
  WakeWord(String, f32),
  AudioLevel(f64),
  Error(String, String),
}

/// Manages the whisperkit-helper subprocess lifecycle.
///
/// The helper owns stdin/stdout pipes permanently until `shutdown()` is
/// called. This lets us send commands and read events across multiple
/// on/off cycles without respawning the process (and losing the in-memory
/// WhisperKit model singleton).
#[derive(Debug)]
pub struct WhisperKitHelper {
  pub process: Option<Child>,
  pub stdin: Option<ChildStdin>,
  /// The helper's stdout wrapped in BufReader for line-based JSON reading.
  /// Taken out during pipeline runs and restored afterward.
  pub reader: Option<BufReader<ChildStdout>>,
}

impl WhisperKitHelper {
  pub fn spawn(helper_path: &str) -> Result<Self, String> {
    let mut child = Command::new(helper_path)
      .stdin(Stdio::piped())
      .stdout(Stdio::piped())
      .stderr(Stdio::piped())
      .spawn()
      .map_err(|e| format!("failed to start whisperkit helper: {e}"))?;

    let stdin = child.stdin.take().ok_or("missing helper stdin".to_string())?;
    let stdout = child.stdout.take().ok_or("missing helper stdout".to_string())?;

    Ok(Self {
      process: Some(child),
      stdin: Some(stdin),
      reader: Some(BufReader::new(stdout)),
    })
  }

  pub fn send_command(&mut self, command_json: &str) -> Result<(), String> {
    let stdin = self.stdin.as_mut().ok_or("helper stdin unavailable".to_string())?;
    stdin
      .write_all(format!("{command_json}\n").as_bytes())
      .map_err(|e| format!("failed to write helper command: {e}"))?;
    stdin.flush().map_err(|e| format!("failed to flush helper command: {e}"))?;
    Ok(())
  }

  pub fn shutdown(&mut self) {
    let _ = self.send_command(r#"{"command":"shutdown"}"#);
    if let Some(child) = self.process.as_mut() {
      let _ = child.kill();
      let _ = child.wait();
    }
    self.stdin = None;
    self.reader = None;
    self.process = None;
  }
}

impl Default for WhisperKitHelper {
  fn default() -> Self {
    Self {
      process: None,
      stdin: None,
      reader: None,
    }
  }
}

pub fn speech_framework_available() -> bool {
  cfg!(target_os = "macos")
}

pub fn helper_binary_path(app: Option<&tauri::AppHandle>) -> String {
  if let Ok(path) = std::env::var("WHISPERKIT_HELPER_PATH") {
    return path;
  }
  if let Some(app) = app {
    if let Ok(resource_dir) = app.path().resource_dir() {
      let bundled = resource_dir.join("whisperkit-helper");
      if bundled.exists() {
        return bundled.to_string_lossy().to_string();
      }
    }
  }
  let cwd_relative = std::env::current_dir()
    .unwrap_or_default()
    .join("whisperkit-helper")
    .join(".build")
    .join("release")
    .join("whisperkit-helper");
  if cwd_relative.exists() {
    return cwd_relative.to_string_lossy().to_string();
  }
  "whisperkit-helper".to_string()
}

pub fn start_wake_listen(
  app: AppHandle,
  stop_flag: Arc<AtomicBool>,
  helper_state: Arc<Mutex<WhisperKitHelper>>,
) {
  let (tx, rx) = crossbeam_channel::unbounded::<VoiceEvent>();
  let app_for_emit = app.clone();
  thread::spawn(move || {
    while let Ok(event) = rx.recv() {
      match event {
        VoiceEvent::Transcript(text, is_final, confidence) => {
          let _ = app_for_emit.emit(
            "owlynn://runtime-event",
            VoiceTranscriptPayload {
              event_type: "voice.transcript",
              text,
              is_final,
              confidence,
            },
          );
        }
        VoiceEvent::WakeWord(phrase, confidence) => {
          let _ = app_for_emit.emit(
            "owlynn://runtime-event",
            VoiceWakeWordPayload {
              event_type: "voice.wake_word",
              phrase,
              confidence,
            },
          );
          let _ = app_for_emit.emit(
            "owlynn://runtime-event",
            VoiceStatePayload {
              event_type: "voice.state",
              state: "recording".to_string(),
            },
          );
        }
        VoiceEvent::AudioLevel(_level) => {}
        VoiceEvent::Error(message, code) => {
          let _ = app_for_emit.emit(
            "owlynn://runtime-event",
            VoiceErrorPayload {
              event_type: "voice.error",
              message,
              code,
            },
          );
        }
      }
    }
  });

  let _app_for_pipeline = app.clone();
  let helper_path = helper_binary_path(Some(&app));
  thread::spawn(move || {
    run_helper_pipeline(&tx, &stop_flag, helper_state, &helper_path);
    let _ = app.emit(
      "owlynn://runtime-event",
      VoiceStatePayload {
        event_type: "voice.state",
        state: "idle".to_string(),
      },
    );
  });
}

fn run_helper_pipeline(
  tx: &crossbeam_channel::Sender<VoiceEvent>,
  stop_flag: &AtomicBool,
  helper_state: Arc<Mutex<WhisperKitHelper>>,
  helper_path: &str,
) {
  let mut is_fresh_spawn = false;

  // Spawn or reuse the helper
  {
    let mut helper = helper_state.lock().unwrap();
    if helper.process.is_none() || helper.stdin.is_none() {
      if helper.process.is_some() {
        helper.shutdown();
      }
      match WhisperKitHelper::spawn(helper_path) {
        Ok(new_helper) => {
          is_fresh_spawn = true;
          *helper = new_helper;
        }
        Err(err) => {
          let _ = tx.send(VoiceEvent::Error(err, "helper_spawn_failed".to_string()));
          return;
        }
      }
    }
    let _ = helper.send_command(
      r#"{"command":"start_wakeword","model":"AthenaSoundClassifier","threshold":0.3}"#,
    );
    if is_fresh_spawn {
      let _ = helper.send_command(r#"{"command":"preload_whisper"}"#);
    }
  }

  // Take the BufReader out of the helper for the pipeline duration.
  let mut reader = {
    let mut helper = helper_state.lock().unwrap();
    helper.reader.take()
  };

  let mut line = String::new();
  loop {
    if stop_flag.load(Ordering::SeqCst) {
      break;
    }
    if reader.is_none() {
      // was restored in a previous iteration (shouldn't happen but guard)
      break;
    }
    let r = reader.as_mut().unwrap();
    line.clear();
    match r.read_line(&mut line) {
      Ok(0) => break,
      Ok(_) => {
        let payload = line.trim();
        if payload.is_empty() {
          continue;
        }
        if payload.contains("\"wakeword_detected\"") {
          let mut helper = helper_state.lock().unwrap();
          let _ = helper.send_command(r#"{"command":"stop_wakeword"}"#);
          let _ = helper.send_command(r#"{"command":"transcribe_start"}"#);
          drop(helper);
          let _ = tx.send(VoiceEvent::WakeWord("Athena".to_string(), 0.9));
          continue;
        }
        if payload.contains("\"transcript\"") {
          let text = extract_json_string_field(payload, "text").unwrap_or_default();
          let is_final = payload.contains("\"is_final\":true");
          let confidence = extract_json_number_field(payload, "confidence").unwrap_or(0.5);
          let _ = tx.send(VoiceEvent::Transcript(text, is_final, confidence));
          continue;
        }
        if payload.contains("\"audio_level\"") {
          if let Some(level) = extract_json_number_field(payload, "level") {
            let _ = tx.send(VoiceEvent::AudioLevel(level as f64));
          }
          continue;
        }
        if payload.contains("\"error\"") {
          let message = extract_json_string_field(payload, "message")
            .unwrap_or_else(|| "unknown helper error".to_string());
          let _ = tx.send(VoiceEvent::Error(message, "helper_error".to_string()));
        }
      }
      Err(e) => {
        let _ = tx.send(VoiceEvent::Error(
          format!("helper stdout read error: {e}"),
          "helper_io_failed".to_string(),
        ));
        break;
      }
    }
  }

  // Restore the BufReader for the next pipeline cycle
  {
    let mut helper = helper_state.lock().unwrap();
    helper.reader = reader.take();
  }

  // Cleanup: stop transcription and wake-word (but keep helper alive)
  let mut helper = helper_state.lock().unwrap();
  let _ = helper.send_command(r#"{"command":"transcribe_stop"}"#);
  let _ = helper.send_command(r#"{"command":"stop_wakeword"}"#);
}

fn extract_json_string_field(payload: &str, key: &str) -> Option<String> {
  let marker = format!("\"{key}\":\"");
  let start = payload.find(&marker)? + marker.len();
  let rest = &payload[start..];
  let end = rest.find('"')?;
  Some(rest[..end].to_string())
}

fn extract_json_number_field(payload: &str, key: &str) -> Option<f32> {
  let marker = format!("\"{key}\":");
  let start = payload.find(&marker)? + marker.len();
  let rest = payload[start..].trim_start();
  let end = rest.find([',', '}']).unwrap_or(rest.len());
  rest[..end].trim().parse::<f32>().ok()
}

pub fn hard_stop_voice(stop_flag: Arc<AtomicBool>, helper_state: Arc<Mutex<WhisperKitHelper>>) {
  stop_flag.store(true, Ordering::SeqCst);
  thread::sleep(Duration::from_millis(50));
  helper_state.lock().unwrap().shutdown();
}

pub fn speak_text(app: AppHandle, text: String, engine: Arc<Mutex<VoiceEngineState>>) -> String {
  let utterance_id = format!(
    "utt-{}",
    std::time::SystemTime::now()
      .duration_since(std::time::UNIX_EPOCH)
      .map(|d| d.as_millis())
      .unwrap_or(0)
  );
  let text_for_tts = text.clone();
  {
    let mut engine = engine.lock().unwrap();
    engine.tts_speaking = true;
  }
  let _ = app.emit(
    "owlynn://runtime-event",
    VoiceTtsStatePayload {
      event_type: "voice.tts_state",
      speaking: true,
      utterance_id: utterance_id.clone(),
    },
  );

  let korean_voice = if text.chars().any(|c| {
    ('\u{AC00}'..='\u{D7AF}').contains(&c) || ('\u{1100}'..='\u{11FF}').contains(&c)
  }) {
    if !Command::new("say")
      .arg("-v")
      .arg("Yuna")
      .arg("test")
      .output()
      .map(|o| o.status.success())
      .unwrap_or(false)
    {
      "Yuna"
    } else {
      ""
    }
  } else {
    ""
  };

  thread::spawn(move || {
    let mut cmd = Command::new("say");
    if !korean_voice.is_empty() {
      cmd.arg("-v").arg(korean_voice);
    }
    cmd.arg(&text_for_tts).output().ok();
    let mut engine = engine.lock().unwrap();
    engine.tts_speaking = false;
    let _ = app.emit(
      "owlynn://runtime-event",
      VoiceTtsStatePayload {
        event_type: "voice.tts_state",
        speaking: false,
        utterance_id,
      },
    );
  });

  text
}
