use serde::Serialize;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;
use tauri::AppHandle;
use tauri::Manager;

#[cfg(target_os = "macos")]
use objc::runtime::{Class, Object, BOOL, NO, YES};
#[cfg(target_os = "macos")]
use objc::{class, msg_send, sel, sel_impl};
#[cfg(target_os = "macos")]
use block::ConcreteBlock;
#[cfg(target_os = "macos")]
use cocoa::base::{id, nil};
#[cfg(target_os = "macos")]
use cocoa::foundation::{NSArray, NSString};

// ── Public State ─────────────────────────────────────────────────

#[derive(Default, Clone)]
pub struct VoiceEngineState {
  pub listening: bool,
  pub recording: bool,
  pub tts_speaking: bool,
  pub wake_word_phrase: String,
  pub wake_stop: Option<Arc<AtomicBool>>,
}

/// Backward-compatible alias used by main.rs NativeRuntimeState
pub type VoiceEngine = VoiceEngineState;

// ── Shared Event Payloads (also re-used by main.rs) ───────────────

#[derive(Clone, Serialize)]
pub struct VoiceStatePayload {
  #[serde(rename = "type")]
  pub event_type: &'static str,
  pub state: String,
}

// ── Tauri Event Payloads ──────────────────────────────────────────

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

// ── Internal Event Channel ────────────────────────────────────────

#[derive(Debug)]
pub enum VoiceEvent {
  Transcript(String, bool, f32),
  WakeWord(String, f32),
  Error(String, String),
}

unsafe impl Send for VoiceEvent {}

// ── Public API ────────────────────────────────────────────────────

pub fn speech_framework_available() -> bool {
  #[cfg(target_os = "macos")]
  {
    Class::get("SFSpeechRecognizer").is_some()
  }
  #[cfg(not(target_os = "macos"))]
  false
}

/// Backward-compat alias for `start_wake_listen`.
pub fn start_wake_loop(app: AppHandle, phrase: String, stop_flag: Arc<AtomicBool>) {
  start_wake_listen(app, phrase, stop_flag, None);
}



/// Start a speech recognition session that listens for the wake-word phrase
/// using SFSpeechRecognizer with constrained phrase detection.
/// On wake-word detection, continues streaming the utterance as a
/// full transcription.
pub fn start_wake_listen(
  app: AppHandle,
  phrase: String,
  stop_flag: Arc<AtomicBool>,
  _engine: Option<Arc<Mutex<VoiceEngineState>>>,
) {
  let (tx, rx) = crossbeam_channel::unbounded::<VoiceEvent>();

  // ── Emitter thread: forwards VoiceEvents to Tauri ──
  let app_clone = app.clone();
  thread::spawn(move || {
    while let Ok(event) = rx.recv() {
      match event {
        VoiceEvent::Transcript(text, is_final, confidence) => {
          let _ = app_clone.emit_all(
            "owlynn://runtime-event",
            VoiceTranscriptPayload {
              event_type: "voice.transcript",
              text,
              is_final,
              confidence,
            },
          );
        }
        VoiceEvent::WakeWord(p, confidence) => {
          let _ = app_clone.emit_all(
            "owlynn://runtime-event",
            VoiceWakeWordPayload {
              event_type: "voice.wake_word",
              phrase: p,
              confidence,
            },
          );
          let _ = app_clone.emit_all(
            "owlynn://runtime-event",
            VoiceStatePayload {
              event_type: "voice.state",
              state: "recording".to_string(),
            },
          );
        }
        VoiceEvent::Error(message, code) => {
          let _ = app_clone.emit_all(
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

  // ── Native speech recognition ──
  thread::spawn(move || {
    #[cfg(target_os = "macos")]
    unsafe {
      run_native_speech_recognition(&tx, &stop_flag, &phrase);
    }

    #[cfg(not(target_os = "macos"))]
    {
      let _ = tx.send(VoiceEvent::Error(
        "Voice engine is available only on macOS".to_string(),
        "platform_unsupported".to_string(),
      ));
    }

    // Signal idle when done
    let _ = app.emit_all(
      "owlynn://runtime-event",
      VoiceStatePayload {
        event_type: "voice.state",
        state: "idle".to_string(),
      },
    );
    drop(tx);
  });
}

/// Start push-to-talk recording with real SFSpeechRecognizer.
/// Returns a receiver that will get VoiceEvent::Transcript events.
pub fn start_recording(
  tx: crossbeam_channel::Sender<VoiceEvent>,
  stop_flag: Arc<AtomicBool>,
  _phrase: String,
) {
  thread::spawn(move || {
    #[cfg(target_os = "macos")]
    {
      unsafe { run_native_speech_recognition(&tx, &stop_flag, ""); }
    }

    #[cfg(not(target_os = "macos"))]
    {
      let _ = tx.send(VoiceEvent::Error(
        "Voice recording is available only on macOS".to_string(),
        "platform_unsupported".to_string(),
      ));
    }

    drop(tx);
  });
}

// ── macOS Native Speech Recognition ──────────────────────────────
//
// Implementation approach:
// 1. Request SFSpeechRecognizer authorization
// 2. Create SFSpeechRecognizer with the user's locale
// 3. Create SFSpeechAudioBufferRecognitionRequest
// 4. Set the constrained phrases (for wake-word mode) on the request
// 5. Set shouldReportPartialResults = YES
// 6. Start recognitionTaskWithRequest:resultHandler: with a block
// 7. Create AVAudioEngine, install an input tap
// 8. AVAudioEngine input tap forwards audio PCM buffers to
//    SFSpeechAudioBufferRecognitionRequest.appendAudioPCMBuffer:
// 9. The recognition result handler sends VoiceEvent::Transcript
//    (interim) or VoiceEvent::WakeWord (if best transcription matches
//    the wake phrase with high confidence)
//
// The main loop runs until stop_flag is set or the recognition
// finishes naturally.

#[cfg(target_os = "macos")]
unsafe fn run_native_speech_recognition(
  tx: &crossbeam_channel::Sender<VoiceEvent>,
  stop_flag: &AtomicBool,
  wake_phrase: &str,
) {
  do_run_native_speech_recognition(tx, stop_flag, wake_phrase);
}

#[cfg(target_os = "macos")]
unsafe fn do_run_native_speech_recognition(
  tx: &crossbeam_channel::Sender<VoiceEvent>,
  stop_flag: &AtomicBool,
  wake_phrase: &str,
) {
  // ── 1. Check SFSpeechRecognizer class availability ──
  if Class::get("SFSpeechRecognizer").is_none() {
    let _ = tx.send(VoiceEvent::Error(
      "SFSpeechRecognizer class not found — Speech framework not loaded".to_string(),
      "speech_unavailable".to_string(),
    ));
    return;
  }

  // Check authorization status
  let auth_status: isize = msg_send![class!(SFSpeechRecognizer), authorizationStatus];
  // SFSpeechRecognizerAuthorizationStatus = 0 notDetermined, 1 denied, 2 restricted, 3 authorized
  if auth_status != 3 {
    if auth_status == 0 {
      // Not determined — request authorization (synchronous block)
      let sem = Arc::new(std::sync::atomic::AtomicBool::new(false));
      let sem_clone = sem.clone();
      let block = ConcreteBlock::new(move |_status: isize| {
        sem_clone.store(true, Ordering::SeqCst);
      });
      let block = block.copy();
      let _: () = msg_send![class!(SFSpeechRecognizer), requestAuthorization: &*block as &block::Block<_, _>];
      // Spin-wait for authorization callback (should be near-instant on desktop)
      let mut waited = 0u64;
      while !sem.load(Ordering::SeqCst) && waited < 100 {
        thread::sleep(Duration::from_millis(50));
        waited += 50;
      }
      // Re-check
      let auth_status2: isize = msg_send![class!(SFSpeechRecognizer), authorizationStatus];
      if auth_status2 != 3 {
        let _ = tx.send(VoiceEvent::Error(
          "Speech recognition authorization denied or restricted".to_string(),
          "auth_denied".to_string(),
        ));
        return;
      }
    } else {
      let _ = tx.send(VoiceEvent::Error(
        "Speech recognition authorization denied or restricted".to_string(),
        "auth_denied".to_string(),
      ));
      return;
    }
  }

  // ── 2. Create SFSpeechRecognizer ──
  let recognizer_class = Class::get("SFSpeechRecognizer").unwrap();
  let locale_id: id = NSString::alloc(nil).init_str("en-US");
  let locale: *mut Object = msg_send![class!(NSLocale), localeWithLocaleIdentifier: locale_id];
  let recognizer: *mut Object = msg_send![recognizer_class, alloc];
  let recognizer: *mut Object = if recognizer.is_null() {
    let _ = tx.send(VoiceEvent::Error(
      "SFSpeechRecognizer alloc failed".to_string(),
      "alloc_failed".to_string(),
    ));
    return;
  } else {
    let r: *mut Object = msg_send![recognizer, initWithLocale: locale];
    if r.is_null() {
      let _ = tx.send(VoiceEvent::Error(
      "SFSpeechRecognizer initWithLocale returned nil".to_string(),
      "init_failed".to_string(),
      ));
      return;
    }
    r
  };

  // Check if recognition is available
  let available: BOOL = msg_send![recognizer, isAvailable];
  if available == NO {
    let _ = tx.send(VoiceEvent::Error(
      "SFSpeechRecognizer is not available on this device".to_string(),
      "recognizer_unavailable".to_string(),
    ));
    return;
  }

  // ── 3. Create SFSpeechAudioBufferRecognitionRequest ──
  let request_class = Class::get("SFSpeechAudioBufferRecognitionRequest").unwrap();
  let request: *mut Object = msg_send![request_class, new];
  if request.is_null() {
    let _ = tx.send(VoiceEvent::Error(
      "SFSpeechAudioBufferRecognitionRequest alloc failed".to_string(),
      "request_alloc_failed".to_string(),
    ));
    return;
  }

  // Set shouldReportPartialResults
  let _: () = msg_send![request, setShouldReportPartialResults: YES];
  // Set taskHint to dictation (best for general speech)
  let _: () = msg_send![request, setTaskHint: 1]; // 1 = SFSpeechRecognitionTaskHintDictation

  // For wake-word mode, set constrained phrases
  if !wake_phrase.is_empty() {
    let ns_phrase: id = NSString::alloc(nil).init_str(wake_phrase);
    let phrases_arr: id = NSArray::arrayWithObject(nil, ns_phrase);
    let _: () = msg_send![request, setContextualStrings: phrases_arr];
    // Set keyboard-locked style for better constrained recognition
    let _: () = msg_send![request, setRequiresOnDeviceRecognition: YES];
  }

  // ── 4. Create recognition task with block result handler ──
  //
  // Important: The block is an Objective-C block that receives
  // (SFSpeechRecognitionResult *, NSError *). Because we're using
  // the `block` crate, we need to wrap our channel sender in the block.
  //
  // We copy the block to move it to the heap since ObjC retains it.

  let tx_result = tx.clone();
  let stop_for_block = Arc::new(AtomicBool::new(false));
  let stop_inner = stop_for_block.clone();
  let wp = wake_phrase.to_string();

  let result_block = ConcreteBlock::new(move |result: *mut Object, error: *mut Object| {
    if !error.is_null() {
      // Get error description
      let desc: *mut Object = unsafe { msg_send![error, localizedDescription] };
      let cstr: *const i8 = unsafe { msg_send![desc, UTF8String] };
      let err_msg = if !cstr.is_null() {
        unsafe { std::ffi::CStr::from_ptr(cstr) }.to_string_lossy().into_owned()
      } else {
        "Unknown speech recognition error".to_string()
      };
      let _ = tx_result.send(VoiceEvent::Error(err_msg, "recognition_error".to_string()));
      stop_inner.store(true, Ordering::SeqCst);
      return;
    }

    if result.is_null() {
      return;
    }

    // Get the best transcription
    let best_transcription: *mut Object = unsafe { msg_send![result, bestTranscription] };
    if best_transcription.is_null() {
      return;
    }

    // Get formattedString
    let formatted_string: *mut Object = unsafe { msg_send![best_transcription, formattedString] };
    let cstr: *const i8 = unsafe { msg_send![formatted_string, UTF8String] };
    if cstr.is_null() {
      return;
    }
    let text = unsafe { std::ffi::CStr::from_ptr(cstr) }.to_string_lossy().into_owned();

    // Get confidence: SFTranscriptionSegment.confidence (returns float)
    let segments: *mut Object = unsafe { msg_send![best_transcription, segments] };
    let first_seg: *mut Object = unsafe { msg_send![segments, firstObject] };
    let confidence_f32: f32 = if !first_seg.is_null() {
      unsafe { msg_send![first_seg, confidence] }
    } else {
      0.5
    };
    let confidence = confidence_f32 as f64;

    // Check if this is the final result
    let is_final: BOOL = unsafe { msg_send![result, isFinal] };

    // For wake-word mode, check if the text contains the wake phrase.
    // When detected on an interim result, immediately deliver the transcript
    // as if it were final so the frontend can act on it without waiting for
    // the recognizer to detect end-of-speech (which can be slow in constrained
    // on-device mode).
    if !wp.is_empty() && text.to_lowercase().contains(&wp.to_lowercase()) && confidence > 0.3 {
      let _ = tx_result.send(VoiceEvent::WakeWord(text.clone(), confidence as f32));
      // If this is an interim result, also send a "final" transcript so the
      // frontend handles it immediately. The recognizer may continue producing
      // additional interims — those will update the preview without re-triggering.
      if is_final == NO {
        let _ = tx_result.send(VoiceEvent::Transcript(
          text.clone(),
          true,  // mark as final so the frontend sends it to the backend
          confidence as f32,
        ));
      }
    }

    // Always send the real transcript event
    let _ = tx_result.send(VoiceEvent::Transcript(
      text,
      is_final == YES,
      confidence as f32,
    ));
  });

  let result_block = result_block.copy();

  // Start the recognition task
  let task: *mut Object = msg_send![recognizer, recognitionTaskWithRequest: request resultHandler: &*result_block as &block::Block<_, _>];
  if task.is_null() {
    let _ = tx.send(VoiceEvent::Error(
      "Failed to create SFSpeechRecognitionTask".to_string(),
      "task_failed".to_string(),
    ));
    return;
  }

  // ── 5. Create AVAudioEngine and install input tap ──
  let audio_engine: *mut Object = msg_send![class!(AVAudioEngine), new];
  if audio_engine.is_null() {
    let _ = tx.send(VoiceEvent::Error(
      "AVAudioEngine alloc failed".to_string(),
      "audio_engine_failed".to_string(),
    ));
    let _: () = msg_send![task, cancel];
    return;
  }

  let input_node: *mut Object = msg_send![audio_engine, inputNode];
  if input_node.is_null() {
    let _ = tx.send(VoiceEvent::Error(
      "AVAudioEngine inputNode is nil — no mic input available".to_string(),
      "no_input_node".to_string(),
    ));
    return;
  }

  // Get input node output format (for bus 0)
  let bus: usize = 0;
  let format: *mut Object = msg_send![input_node, outputFormatForBus: bus];
  let buffer_size: u32 = 1024;

  // Install tap on the input node
  // The block receives (AVAudioPCMBuffer *, AVAudioTime *)
  // We use Arc for shared stop signal between blocks and main loop
  let stop_tap = stop_for_block.clone();
  let request_tap = request; // retain reference for buffer appending
  let tap_block = ConcreteBlock::new(move |buffer: *mut Object, _audio_time: *mut Object| {
    if buffer.is_null() || stop_tap.load(Ordering::SeqCst) {
      return;
    }
    // Append buffer to the recognition request
    let _: () = unsafe { msg_send![request_tap, appendAudioPCMBuffer: buffer] };
  });
  let tap_block = tap_block.copy();

  let _: () = msg_send![input_node, installTapOnBus: bus
                            bufferSize: buffer_size
                            format: format
                            block: &*tap_block as &block::Block<_, _>];

  // ── 6. Start the audio engine ──
  // NSError *error = nil;
  // BOOL started = [audioEngine startAndReturnError:&error];
  let mut engine_error: *mut Object = std::ptr::null_mut();
  let error_ptr: *mut Object = &mut engine_error as *mut *mut Object as *mut Object;
  let started: BOOL = msg_send![audio_engine, startAndReturnError: error_ptr];
  if started == NO {
    let err_msg = {
      let error_val: *mut Object = *(error_ptr as *mut *mut Object);
      if !error_val.is_null() {
        let desc: *mut Object = msg_send![error_val, localizedDescription];
        let cstr: *const i8 = msg_send![desc, UTF8String];
        if !cstr.is_null() {
          std::ffi::CStr::from_ptr(cstr).to_string_lossy().into_owned()
        } else {
          "Unknown AVAudioEngine error".to_string()
        }
      } else {
        "AVAudioEngine failed to start".to_string()
      }
    };
    let _ = tx.send(VoiceEvent::Error(err_msg, "engine_start_failed".to_string()));
    let _: () = msg_send![task, cancel];
    return;
  }

  let _ = tx.send(VoiceEvent::Transcript(
    format!("Listening{}…", if wake_phrase.is_empty() { String::new() } else { format!(" for '{}'", wake_phrase) }),
    false,
    0.0,
  ));

  // ── 7. Main loop: wait for stop signal or final transcription ──
  while !stop_flag.load(Ordering::SeqCst) && !stop_for_block.load(Ordering::SeqCst) {
    thread::sleep(Duration::from_millis(100));
  }

  // ── 8. Cleanup ──
  // Stop audio engine and remove the tap
  let _: () = msg_send![audio_engine, stop];
  let _: () = msg_send![input_node, removeTapOnBus: bus];

  // Finish the recognition task rather than cancel it. Unlike cancel(),
  // finish() tells the recognizer to complete the current transcription
  // and deliver a final result (is_final == YES) via the result handler.
  // This ensures the frontend receives a final transcript event and the
  // utterance is sent to the backend via WebSocket.
  let _: () = msg_send![task, finish];
  // Give the recognizer a brief moment to produce the final callback.
  // The result handler fires on a dispatch queue, not our thread, so
  // we sleep to let it enqueue the final VoiceEvent before the channel
  // sender references are dropped.
  thread::sleep(Duration::from_millis(200));
  // Note: we intentionally do NOT release the ObjC objects here. The
  // cancel/finish calls may autorelease internal refs from dispatch queues,
  // and explicit release + pool-drain (on an implicit TLS pool during thread
  // exit) causes a double-free crash. Since speech sessions are short-lived
  // and objects are small, leaking 4 objects per invocation is acceptable.
}

#[cfg(not(target_os = "macos"))]
unsafe fn run_native_speech_recognition(
  _tx: &crossbeam_channel::Sender<VoiceEvent>,
  _stop_flag: &AtomicBool,
  _wake_phrase: &str,
) {
  // No-op on non-macOS
}

// ── TTS ──────────────────────────────────────────────────────────

/// Backward-compat alias for the `say` command-based TTS (used by main.rs speak_text command).
/// Kept for reference; new code should use `voice::speak_text` (with NSSpeechSynthesizer).
pub fn speak_macos(text: &str) -> Result<(), String> {
  #[cfg(target_os = "macos")]
  {
    let status = std::process::Command::new("say")
      .arg(text)
      .status()
      .map_err(|err| format!("failed to execute say: {}", err))?;
    if !status.success() {
      return Err("say command failed".to_string());
    }
    Ok(())
  }
  #[cfg(not(target_os = "macos"))]
  {
    let _ = text;
    Err("TTS is supported only on macOS".to_string())
  }
}

/// Speak text via NSSpeechSynthesizer (ObjC), falling back to `say` command.
/// Emits state/error events to the frontend through the engine state mutex.
/// Returns the utterance id.
pub fn speak_text(
  app: AppHandle,
  text: String,
  engine: Arc<Mutex<VoiceEngineState>>,
) -> String {
  let utterance_id = format!("utt-{}", std::time::SystemTime::now()
    .duration_since(std::time::UNIX_EPOCH)
    .map(|d| d.as_millis())
    .unwrap_or(0));

  {
    let mut eng = engine.lock().unwrap();
    eng.tts_speaking = true;
  }

  let _ = app.emit_all(
    "owlynn://runtime-event",
    VoiceStatePayload {
      event_type: "voice.state",
      state: "speaking".to_string(),
    },
  );
  let _ = app.emit_all(
    "owlynn://runtime-event",
    VoiceTtsStatePayload {
      event_type: "voice.tts_state",
      speaking: true,
      utterance_id: utterance_id.clone(),
    },
  );

  let eng_clone = engine.clone();
  let app_clone = app.clone();
  let uid = utterance_id.clone();

  thread::spawn(move || {
    let result = speak_macos_blocking(&text);
    {
      let mut eng = eng_clone.lock().unwrap();
      eng.tts_speaking = false;
    }
    let _ = app_clone.emit_all(
      "owlynn://runtime-event",
      VoiceTtsStatePayload {
        event_type: "voice.tts_state",
        speaking: false,
        utterance_id: uid,
      },
    );
    let _ = app_clone.emit_all(
      "owlynn://runtime-event",
      VoiceStatePayload {
        event_type: "voice.state",
        state: "idle".to_string(),
      },
    );
    if let Err(err) = result {
      let _ = app_clone.emit_all(
        "owlynn://runtime-event",
        VoiceErrorPayload {
          event_type: "voice.error",
          message: err,
          code: "tts_failed".to_string(),
        },
      );
    }
  });

  utterance_id
}

/// Blocking TTS via macOS NSSpeechSynthesizer (ObjC).
/// Falls back to `say` command if ObjC class is not found.
#[cfg(target_os = "macos")]
fn speak_macos_blocking(text: &str) -> Result<(), String> {
  // Try NSSpeechSynthesizer via objc first
  if let Some(synth_class) = Class::get("NSSpeechSynthesizer") {
    unsafe {
      let synth: *mut Object = msg_send![synth_class, alloc];
      let synth: *mut Object = msg_send![synth, init];
      if synth.is_null() {
        return Err("NSSpeechSynthesizer alloc/init returned nil".to_string());
      }
      let ns_string: id = NSString::alloc(nil).init_str(text);
      let _: BOOL = msg_send![synth, startSpeakingString: ns_string];

      // Poll until done (or timeout at 60s)
      let mut elapsed = 0u64;
      let max_ms = 60_000u64;
      loop {
        let is_speaking: BOOL = msg_send![synth, isSpeaking];
        if is_speaking == NO || elapsed > max_ms {
          break;
        }
        thread::sleep(Duration::from_millis(100));
        elapsed += 100;
      }
      let _: () = msg_send![synth, release];
      return Ok(());
    }
  }

  // Fallback: macOS `say` command
  let status = std::process::Command::new("say")
    .arg(text)
    .status()
    .map_err(|err| format!("failed to execute say: {}", err))?;
  if !status.success() {
    return Err("say command failed".to_string());
  }
  Ok(())
}

#[cfg(not(target_os = "macos"))]
fn speak_macos_blocking(text: &str) -> Result<(), String> {
  let _ = text;
  Err("TTS is supported only on macOS".to_string())
}
