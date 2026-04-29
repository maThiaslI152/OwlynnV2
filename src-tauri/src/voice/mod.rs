use serde::Serialize;
use std::process::Command;
use std::sync::{Arc, Mutex};
use std::thread;
use tauri::{AppHandle, Emitter};

#[derive(Default, Clone)]
#[allow(dead_code)]
pub struct VoiceEngineState {
  pub listening: bool,
  pub tts_speaking: bool,
  pub wake_word_phrase: String,
  pub wake_stop: Option<Arc<std::sync::atomic::AtomicBool>>,
}

pub type VoiceEngine = VoiceEngineState;

#[derive(Clone, Serialize)]
pub struct VoiceTtsStatePayload {
  #[serde(rename = "type")]
  pub event_type: &'static str,
  pub speaking: bool,
  pub utterance_id: String,
}

pub fn speak_text(
  app: AppHandle,
  text: String,
  engine: Arc<Mutex<VoiceEngineState>>,
) -> String {
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
    if Command::new("say")
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
