# Tests for deepwork/feedback/messages.py and tts.py — OpenAI text calls are
# faked (no network); the TTS queue is tested with an injected speak function.

import struct
import time

from deepwork.feedback.messages import MessageGenerator, build_prompt
from deepwork.feedback.tts import SpeechQueue, fix_streamed_wav_header
from deepwork.storage import ResultsStore


class FakeResponses:
    def __init__(self):
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        class R:                                    # stand-in for Response
            output_text = "You've got this!"        # SDK convenience property:
            # https://github.com/openai/openai-python (responses.create)
            def model_dump(self):
                return {"output_text": self.output_text}
        return R()


class FakeClient:
    def __init__(self):
        self.responses = FakeResponses()


def test_build_prompt_covers_all_message_kinds():
    # Each spec message type has a dedicated prompt containing its context.
    assert "write thesis" in build_prompt("good_luck", topic="write thesis")
    p = build_prompt("nudge", topic="thesis", reason="watching videos")
    assert "watching videos" in p and "gentle" in p.lower()
    p = build_prompt("praise", topic="thesis", reason="focused coding")
    assert "30" in p                                # praise is for 30 minutes
    p = build_prompt("break_ack", purpose="coffee", minutes=10)
    assert "coffee" in p and "10" in p


def test_generator_calls_llm_and_persists_exchange(tmp_path):
    client = FakeClient()
    gen = MessageGenerator(client=client, model="test-model",
                           store=ResultsStore(tmp_path))
    text = gen.generate("good_luck", topic="write thesis")
    assert text == "You've got this!"
    assert client.responses.last_kwargs["model"] == "test-model"
    # Full exchange saved to results/llm/ (spec: outputs logged uncut).
    assert list((tmp_path / "llm").glob("*_message.json"))


def test_speech_queue_speaks_in_order_and_survives_errors():
    spoken = []
    def speak(text):
        if text == "boom":
            raise RuntimeError("engine hiccup")    # must not kill the worker
        spoken.append(text)
    q = SpeechQueue(speak)
    q.say("one"); q.say("boom"); q.say("two")
    # queue.join() blocks until every enqueued item is processed:
    # https://docs.python.org/3/library/queue.html#queue.Queue.join
    q.wait_idle(timeout=5)
    q.stop()
    assert spoken == ["one", "two"]                # order kept, error skipped


def test_fix_streamed_wav_header_patches_placeholder_sizes(tmp_path):
    # OpenAI's STREAMED wav responses carry 0xFFFFFFFF in the RIFF and data
    # chunk size fields (length unknown at stream start) — winsound silently
    # refuses such files, which made TTS inaudible. Build a minimal RIFF/WAVE
    # with the same placeholder sizes and assert both get patched to reality.
    # RIFF layout: http://soundfile.sapp.org/doc/WaveFormat/
    fmt = struct.pack("<4sIHHIIHH", b"fmt ", 16, 1, 1, 24000, 48000, 2, 16)
    pcm = b"\x00\x00" * 100                        # 100 silent samples
    body = b"WAVE" + fmt + b"data" + struct.pack("<I", 0xFFFFFFFF) + pcm
    wav = tmp_path / "streamed.wav"
    wav.write_bytes(b"RIFF" + struct.pack("<I", 0xFFFFFFFF) + body)

    fix_streamed_wav_header(wav)

    data = wav.read_bytes()
    assert struct.unpack_from("<I", data, 4)[0] == len(data) - 8
    i = data.find(b"data")
    assert struct.unpack_from("<I", data, i + 4)[0] == len(data) - i - 8


def test_fix_streamed_wav_header_ignores_non_riff(tmp_path):
    # Defensive: a non-WAV file must pass through untouched, not crash.
    f = tmp_path / "not.wav"
    f.write_bytes(b"ID3\x03something-mp3ish")
    fix_streamed_wav_header(f)
    assert f.read_bytes() == b"ID3\x03something-mp3ish"


def test_speech_queue_stop_terminates_worker():
    q = SpeechQueue(lambda t: None)
    q.stop()
    time.sleep(0.05)
    assert not q.thread.is_alive()                 # daemon thread exited
