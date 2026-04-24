use serde::Serialize;
use std::io::{BufRead, BufReader, Write};
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;
use tauri::{AppHandle, Emitter};

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
  Error(String, String),
}

#[derive(Debug, Default)]
pub struct WhisperKitHelper {
  pub process: Option<Child>,
  pub stdin: Option<ChildStdin>,
  pub stdout: Option<ChildStdout>,
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
      stdout: Some(stdout),
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

  pub fn take_stdout(&mut self) -> Option<ChildStdout> {
    self.stdout.take()
  }

  pub fn shutdown(&mut self) {
    let _ = self.send_command(r#"{"command":"shutdown"}"#);
    if let Some(child) = self.process.as_mut() {
      let _ = child.kill();
      let _ = child.wait();
    }
    self.stdin = None;
    self.stdout = None;
    self.process = None;
  }
}

pub fn speech_framework_available() -> bool {
  cfg!(target_os = "macos")
}

pub fn helper_binary_path() -> String {
  std::env::var("WHISPERKIT_HELPER_PATH")
    .unwrap_or_else(|_| "src-tauri/whisperkit-helper/.build/release/whisperkit-helper".to_string())
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

  thread::spawn(move || {
    run_helper_pipeline(&tx, &stop_flag, helper_state);
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
) {
  let helper_path = helper_binary_path();
  {
    let mut helper = helper_state.lock().unwrap();
    if helper.process.is_none() {
      match WhisperKitHelper::spawn(&helper_path) {
        Ok(new_helper) => *helper = new_helper,
        Err(err) => {
          let _ = tx.send(VoiceEvent::Error(err, "helper_spawn_failed".to_string()));
          return;
        }
      }
    }
    let _ = helper.send_command(r#"{"command":"start_wakeword","model":"AthenaSoundClassifier","threshold":0.3}"#);
    let _ = helper.send_command(r#"{"command":"transcribe_start","audio_format":{"sample_rate":16000}}"#);
  }

  let stdout = {
    let mut helper = helper_state.lock().unwrap();
    helper.take_stdout()
  };

  let Some(stdout) = stdout else {
    let _ = tx.send(VoiceEvent::Error(
      "helper stdout unavailable".to_string(),
      "helper_io_failed".to_string(),
    ));
    return;
  };

  let reader = BufReader::new(stdout);
  for line in reader.lines() {
    if stop_flag.load(Ordering::SeqCst) {
      break;
    }
    let Ok(payload) = line else {
      continue;
    };
    if payload.contains("\"wakeword_detected\"") {
      let _ = tx.send(VoiceEvent::WakeWord("Athena".to_string(), 0.9));
      continue;
    }
    if payload.contains("\"transcript\"") {
      let text = extract_json_string_field(&payload, "text").unwrap_or_default();
      let is_final = payload.contains("\"is_final\":true");
      let confidence = extract_json_number_field(&payload, "confidence").unwrap_or(0.5);
      let _ = tx.send(VoiceEvent::Transcript(text, is_final, confidence));
      continue;
    }
    if payload.contains("\"error\"") {
      let message = extract_json_string_field(&payload, "message")
        .unwrap_or_else(|| "unknown helper error".to_string());
      let _ = tx.send(VoiceEvent::Error(message, "helper_error".to_string()));
    }
  }

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

  {
    let mut eng = engine.lock().unwrap();
    eng.tts_speaking = true;
  }

  let _ = app.emit(
    "owlynn://runtime-event",
    VoiceStatePayload {
      event_type: "voice.state",
      state: "speaking".to_string(),
    },
  );
  let _ = app.emit(
    "owlynn://runtime-event",
    VoiceTtsStatePayload {
      event_type: "voice.tts_state",
      speaking: true,
      utterance_id: utterance_id.clone(),
    },
  );

  let app_clone = app.clone();
  let uid = utterance_id.clone();
  thread::spawn(move || {
    #[cfg(target_os = "macos")]
    let tts_result = Command::new("say").arg(&text).status();
    #[cfg(not(target_os = "macos"))]
    let tts_result: Result<std::process::ExitStatus, std::io::Error> =
      Err(std::io::Error::new(std::io::ErrorKind::Unsupported, "tts unsupported"));

    let _ = app_clone.emit(
      "owlynn://runtime-event",
      VoiceTtsStatePayload {
        event_type: "voice.tts_state",
        speaking: false,
        utterance_id: uid,
      },
    );
    let _ = app_clone.emit(
      "owlynn://runtime-event",
      VoiceStatePayload {
        event_type: "voice.state",
        state: "idle".to_string(),
      },
    );
    if let Err(err) = tts_result {
      let _ = app_clone.emit(
        "owlynn://runtime-event",
        VoiceErrorPayload {
          event_type: "voice.error",
          message: format!("tts failed: {err}"),
          code: "tts_failed".to_string(),
        },
      );
    }
  });

  utterance_id
}
