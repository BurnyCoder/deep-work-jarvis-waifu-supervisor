# Text-to-speech (requirement 4). Two engines behind one speak(text) door:
#  - "openai": natural voice via the TTS API, written to a temp WAV and
#    played with the stdlib winsound module (no extra audio dependency)
#    https://developers.openai.com/api/docs/guides/text-to-speech
#  - "pyttsx3": offline Windows SAPI5 fallback (free, robotic, no network)
#    https://pypi.org/project/pyttsx3/
# All speech is serialized through ONE worker thread (SpeechQueue) because
# pyttsx3 is not thread-safe and overlapping WAV playback is unintelligible.

import logging
import queue
import struct
import tempfile
import threading
from pathlib import Path

log = logging.getLogger(__name__)


def fix_streamed_wav_header(path: Path) -> None:
    """Patch the RIFF/data chunk sizes of a STREAMED wav file.

    The TTS API streams audio before knowing its length, so the wav header's
    RIFF size and data-chunk size fields arrive as the 0xFFFFFFFF placeholder
    (verified live 2026-07-07). winsound.PlaySound silently rejects such
    files — the bug that made all spoken feedback inaudible. Rewriting both
    fields from the real file size makes the file spec-valid.
    RIFF layout reference: http://soundfile.sapp.org/doc/WaveFormat/
    """
    data = bytearray(path.read_bytes())
    if data[:4] != b"RIFF" or len(data) < 44:      # not a wav → leave alone
        return
    # Bytes 4-8: total RIFF chunk size = file size minus the 8-byte header.
    # struct '<I' = little-endian uint32: https://docs.python.org/3/library/struct.html
    struct.pack_into("<I", data, 4, len(data) - 8)
    i = data.find(b"data")                         # start of the data chunk
    if i != -1:
        # data chunk size = everything after its own 8-byte chunk header.
        struct.pack_into("<I", data, i + 4, len(data) - i - 8)
    path.write_bytes(data)


def make_openai_speaker(client, model: str, voice: str):
    """Return a speak(text) closure using the OpenAI TTS API."""
    def speak(text: str) -> None:
        # NamedTemporaryFile(delete=False) because winsound needs a real path
        # it can reopen: https://docs.python.org/3/library/tempfile.html
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wav_path = Path(f.name)
        # with_streaming_response streams audio straight to disk — documented
        # pattern at https://developers.openai.com/api/docs/guides/text-to-speech
        with client.audio.speech.with_streaming_response.create(
                model=model, voice=voice, input=text,
                response_format="wav") as response:
            response.stream_to_file(wav_path)
        # Streamed wav headers carry placeholder sizes that winsound rejects
        # SILENTLY (no exception, no sound) — patch them before playback.
        fix_streamed_wav_header(wav_path)
        import winsound  # Windows-only stdlib: https://docs.python.org/3/library/winsound.html
        # SND_FILENAME plays a WAV file synchronously (returns when done).
        winsound.PlaySound(str(wav_path), winsound.SND_FILENAME)
        wav_path.unlink(missing_ok=True)          # tidy the temp file
    return speak


def make_pyttsx3_speaker():
    """Return a speak(text) closure using the offline SAPI5 voice."""
    def speak(text: str) -> None:
        import pyttsx3                             # import here: only if used
        engine = pyttsx3.init()                    # fresh engine per utterance
        engine.say(text)                           # queue the phrase
        engine.runAndWait()                        # block until spoken
        # A fresh init per call avoids the long-standing "second runAndWait
        # never returns" reuse bug: https://github.com/nateshmbhat/pyttsx3/issues/193
    return speak


def make_speaker(cfg, client):
    # Engine chosen by TTS_ENGINE in .env; openai needs the shared client.
    if cfg.tts_engine == "openai":
        return make_openai_speaker(client, cfg.tts_model, cfg.tts_voice)
    return make_pyttsx3_speaker()


class SpeechQueue:
    """FIFO speech: say() never blocks the caller; one daemon thread speaks."""

    # None is the sentinel that tells the worker to exit — the documented
    # queue shutdown idiom: https://docs.python.org/3/library/queue.html
    _STOP = None

    def __init__(self, speak_fn):
        self._speak = speak_fn
        self._q: queue.Queue = queue.Queue()
        # daemon=True so a crashed main thread never hangs on speech:
        # https://docs.python.org/3/library/threading.html#threading.Thread.daemon
        self.thread = threading.Thread(target=self._run, daemon=True, name="tts")
        self.thread.start()

    def say(self, text: str) -> None:
        log.info("speaking: %s", text)             # every utterance logged
        self._q.put(text)

    def _run(self) -> None:
        while True:
            text = self._q.get()                   # blocks until work arrives
            try:
                if text is self._STOP:
                    return
                self._speak(text)
            except Exception:                      # engine hiccup ≠ dead queue
                log.exception("TTS failed for: %s", text)
            finally:
                self._q.task_done()                # pairs with q.join()

    def wait_idle(self, timeout: float | None = None) -> None:
        # queue.join() has no timeout parameter, so poll unfinished_tasks —
        # used by tests and the --smoke one-shot to wait for speech to finish.
        import time
        deadline = time.monotonic() + (timeout or 0)
        while self._q.unfinished_tasks:
            if timeout and time.monotonic() > deadline:
                return
            time.sleep(0.01)

    def stop(self) -> None:
        self._q.put(self._STOP)                    # wake worker → clean exit
