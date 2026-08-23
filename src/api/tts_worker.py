import logging
from queue import Queue
from threading import Thread

logger = logging.getLogger(__name__)


class TTSWorker:
    """
    Background worker for Text-to-Speech streaming.
    Designed to use Kokoro-82M for fast, high-quality local TTS.
    """

    def __init__(self):
        self.queue = Queue()
        self.thread = Thread(target=self._run, daemon=True)
        self.is_running = False

    def start(self):
        if not self.is_running:
            self.is_running = True
            self.thread.start()
            logger.info("TTS Worker started.")

    def stop(self):
        self.is_running = False
        self.queue.put(None)  # Poison pill

    def enqueue_text(self, text: str):
        if self.is_running and text.strip():
            self.queue.put(text.strip())

    def _run(self):
        import importlib.util

        has_kokoro = importlib.util.find_spec("kokoro") is not None
        if not has_kokoro:
            logger.info("Kokoro-82M not installed. TTS will run in logging-only mode.")

        while self.is_running:
            try:
                text = self.queue.get()
                if text is None:
                    break

                if has_kokoro:
                    logger.debug("[TTS] Generating speech for: %s...", text[:30])
                    # Placeholder for actual Kokoro synthesize call
                    # audio = kokoro.synthesize(text, voice="af")
                    # kokoro.play(audio)
                else:
                    logger.debug("[TTS-STUB] %s", text)

                self.queue.task_done()
            except Exception as e:
                logger.error("Error in TTS Worker: %s", e)


# Global singleton
tts_manager = TTSWorker()
