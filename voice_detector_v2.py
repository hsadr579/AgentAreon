import sounddevice as sd
import threading as t
import numpy as np
import whisper
import queue
import time
import json
import random
import re
import webrtcvad

import speaker_v3 as speaker


# ─────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────

CONFIG_FILE        = "config.json"
SYNC_INSTRUCTIONS  = "sync_instructions.json"

THE_NAME   = "Agent Areon"
STOP_NAME  = "sleep now"

# How many consecutive speech frames before we start recording
SPEECH_HITS_REQUIRED = 3

# How long silence ends a segment (seconds)
SILENCE_GAP_SEC = 0.45

# Hard cap on a single utterance (seconds)
MAX_SEGMENT_SEC = 10

LISTEN_DURING_SPEAK=True

RESPONSE_MSG = [
    "At your service",
    "My lord",
    "Agent Areon listening",
]

VOICE_OFF_MSG = [
    "I shall take my leave",
]

try:
    with open(CONFIG_FILE, "r") as fp:
        configs = json.load(fp)
        THE_NAME          = configs.get("voice_summoning_word",    THE_NAME)
        RESPONSE_MSG      = configs.get("voice_summoning_answers", RESPONSE_MSG)
        STOP_NAME      = configs.get("voice_stopping_word", STOP_NAME)
        MAX_SEGMENT_SEC      = configs.get("voice_max_seg_length", MAX_SEGMENT_SEC)
        SILENCE_GAP_SEC      = configs.get("voice_max_silence_gap", SILENCE_GAP_SEC)
        LISTEN_DURING_SPEAK      = configs.get("voice_listen_during_speak", LISTEN_DURING_SPEAK)
except Exception:
    pass


# ─────────────────────────────────────────
# AUDIO / VAD CONSTANTS
# ─────────────────────────────────────────

SAMPLERATE    = 16000
FRAME_MS      = 30
FRAME_SAMPLES = SAMPLERATE * FRAME_MS // 1000   # 480 samples
BLOCKSIZE     = FRAME_SAMPLES

vad = webrtcvad.Vad(2)





# ── Barge-in tuning ────────────────────────────────────────────────────────────
#
# While TTS is playing the mic picks up speaker leakage.  We need to tell apart
# "user is talking" from "that's just the speaker bleeding into the mic".
#
# Strategy:
#   1. We keep running energy + VAD even while the TTS is playing.
#   2. We require BOTH high energy AND VAD-confirmed speech to call it a barge-in.
#   3. After BARGE_IN_HITS consecutive frames that pass both tests we interrupt TTS.
#   4. Critically: we keep the audio that triggered the barge-in so we can
#      transcribe it — you don't have to repeat yourself.
#   5. After TTS stops we wait ECHO_COOLDOWN_SEC before reactivating normal VAD
#      so the speaker ring-out doesn't sneak in as a false utterance.
#
# BARGE_IN_ENERGY_THRESHOLD – raise this if your speakers are loud and bleed
#                              into the mic; lower it if you have to shout to
#                              interrupt.  0.008 is a safe starting point.
#
BARGE_IN_HITS              = 4
BARGE_IN_ENERGY_THRESHOLD  = 0.008   # RMS²  (tune per your hardware)
ECHO_COOLDOWN_SEC          = 0.40    # seconds to ignore audio after TTS stops


# ─────────────────────────────────────────
# WHISPER
# ─────────────────────────────────────────

model = whisper.load_model("base")


# ─────────────────────────────────────────
# GLOBALS
# ─────────────────────────────────────────

audio_q    = queue.Queue()
voice_thread = None
stop_vd    = False
IS_LISTENING = False


# ─────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────

def audio_callback(indata, frames, time_info, status):
    audio_q.put(indata.copy())


def mono(audio):
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim > 1:
        audio = audio[:, 0]
    return audio


def is_likely_speech(audio):
    """WebRTC VAD check on the first 30-ms frame."""
    if len(audio) < FRAME_SAMPLES:
        return False
    frame = audio[:FRAME_SAMPLES]
    if np.max(np.abs(frame)) < 0.01:       # dead-silent fast-path
        return False
    pcm = np.clip(frame * 32768, -32768, 32767).astype(np.int16)
    try:
        return vad.is_speech(pcm.tobytes(), SAMPLERATE)
    except Exception:
        return False


def stop_tts():
   
    """Best-effort TTS stop — works with speaker_v3 and older variants."""
    if hasattr(speaker, "stop_and_clear"):
        try:
            speaker.stop_and_clear()
            return
        except Exception:
            pass
    # fallback
    try:
        speaker.SPEAKING = False
        speaker.speech_queue.clear()
        sd.stop()
    except Exception:
        pass


def transcribe(audio):
    if len(audio) < SAMPLERATE * 0.25:
        return ""
    try:
        result = model.transcribe(
            audio,
            language="en",
            initial_prompt=f"{THE_NAME}, {STOP_NAME}",
            no_speech_threshold=0.6,
            logprob_threshold=-1.0,
            condition_on_previous_text=False,
            fp16=False,
        )
        return result["text"].strip()
    except Exception:
        return ""


def keyword_remainder(text, keyword):
    """Return whatever comes after 'keyword' in text, or '' if not found."""
    pattern = re.compile(r"\b" + re.escape(keyword.lower()) + r"\b")
    match = pattern.search(text.lower())
    if not match:
        return ""
    return text[match.end():].strip(" ,.!?:;")


def save_instruction(text):
    data = {"instructions": []}
    try:
        with open(SYNC_INSTRUCTIONS, "r") as fp:
            data = json.load(fp)
        if "instructions" not in data:
            data = {"instructions": []}
    except Exception:
        pass
    data["instructions"].append(["voice", text])
    with open(SYNC_INSTRUCTIONS, "w") as fp:
        json.dump(data, fp)


# ─────────────────────────────────────────
# MAIN LISTEN LOOP
# ─────────────────────────────────────────

def listen():
    global stop_vd, IS_LISTENING

    state = "SLEEPING"   # "SLEEPING" | "AWAKE"

    # ── recording state ──
    segment: list       = []
    segment_start       = None
    last_voice          = None
    speech_hits         = 0

    # ── barge-in state ──
    barge_hits          = 0
    barge_buffer: list  = []   # audio frames captured during barge-in attempt

    # ── post-TTS cooldown ──
    tts_was_speaking    = False
    ignore_until        = 0.0

    with sd.InputStream(
        samplerate=SAMPLERATE,
        channels=1,
        callback=audio_callback,
        blocksize=BLOCKSIZE,
    ):
        while not stop_vd:

            try:
                data = audio_q.get(timeout=0.2)
            except queue.Empty:
                continue

            now   = time.time()
            audio = mono(data)

            # ── post-TTS echo cooldown ──────────────────────────────────────
            currently_speaking = False if LISTEN_DURING_SPEAK else getattr(speaker, "SPEAKING", False)

            if tts_was_speaking and not currently_speaking:
                # TTS just stopped — start cooldown, reset barge state
                ignore_until     = now + ECHO_COOLDOWN_SEC
                barge_hits       = 0
                barge_buffer     = []
                tts_was_speaking = False

            tts_was_speaking = currently_speaking

            if now < ignore_until:
                continue

            # ── BARGE-IN DETECTION (runs while TTS is playing) ─────────────
            if currently_speaking:
                continue
                energy = float(np.mean(audio ** 2))
                speech = is_likely_speech(audio)

                if energy > BARGE_IN_ENERGY_THRESHOLD and speech:
                    barge_hits += 1
                    barge_buffer.append(audio)
                else:
                    # decay — one bad frame won't kill a real attempt
                    barge_hits = max(0, barge_hits - 1)
                    if barge_hits == 0:
                        barge_buffer = []

                if barge_hits >= BARGE_IN_HITS:
                    print("[VOICE] Barge-in detected — interrupting TTS")
                    stop_tts()

                    # Keep the barge-in audio so we can transcribe it
                    # (the ignore_until cooldown is set above on the next frame
                    #  when SPEAKING flips to False, so we won't double-count)
                    if state == "AWAKE" and barge_buffer:
                        saved = list(barge_buffer)  # capture before reset
                        def _transcribe_barge(frames):
                            combined = np.concatenate(frames)
                            text = transcribe(combined)
                            if text:
                                print("[VOICE] (barge-in)", text)
                                _handle_awake_text(text)
                        t.Thread(target=_transcribe_barge, args=(saved,), daemon=True).start()

                    barge_hits   = 0
                    barge_buffer = []
                    # reset normal segment so we start fresh after cooldown
                    segment       = []
                    segment_start = None
                    last_voice    = None
                    speech_hits   = 0

                continue   # don't run normal VAD while TTS is live

            # ── NORMAL VAD ─────────────────────────────────────────────────
            barge_hits   = 0
            barge_buffer = []

            speech = is_likely_speech(audio)
            if speech:
                speech_hits += 1
            else:
                speech_hits = max(0, speech_hits - 1)

            confirmed = speech_hits >= SPEECH_HITS_REQUIRED

            if confirmed:
                if segment_start is None:
                    segment_start = now
                    segment = []
                segment.append(audio)
                last_voice = now

            # Nothing recorded yet — nothing to finalize
            if segment_start is None or last_voice is None:
                continue

            silence  = now - last_voice
            duration = now - segment_start

            # Still within the utterance
            if silence < SILENCE_GAP_SEC and duration < MAX_SEGMENT_SEC:
                continue

            # ── FINALIZE SEGMENT ───────────────────────────────────────────
            speech_hits   = 0
            captured      = segment[:]
            segment       = []
            segment_start = None
            last_voice    = None

            try:
                full_audio = np.concatenate(captured)
            except ValueError:
                continue

            text = transcribe(full_audio)
            if not text:
                continue
            stop_tts()
            print("[VOICE]", text)

            lower = text.lower()

            # ── SLEEPING: wait for wake word ───────────────────────────────
            if state == "SLEEPING":
                if THE_NAME.lower() not in lower:
                    continue

                state        = "AWAKE"
                IS_LISTENING = True

                speaker.speech_queue.append(random.choice(RESPONSE_MSG))

                # If they said something after the wake word, handle it now
                remain = keyword_remainder(text, THE_NAME)
                if remain:
                    _handle_awake_text(remain)

                continue

            # ── AWAKE ──────────────────────────────────────────────────────
            _handle_awake_text(text)

            if STOP_NAME.lower() in text.lower():
                state        = "SLEEPING"
                IS_LISTENING = False


# ─────────────────────────────────────────
# COMMAND ROUTING (extracted so barge-in
# can reuse the same logic)
# ─────────────────────────────────────────

def _handle_awake_text(text):
    global IS_LISTENING
    lower = text.lower()

    if STOP_NAME.lower() in lower:
        print("[VOICE] Going to sleep")
        speaker.speech_queue.append(random.choice(VOICE_OFF_MSG))
        IS_LISTENING = False
        return

    save_instruction(text)
    IS_LISTENING = True


# ─────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────

def run_voice_detector():
    global voice_thread, stop_vd, IS_LISTENING
    stop_vd      = False
    IS_LISTENING = False
    voice_thread = t.Thread(target=listen, daemon=True)
    voice_thread.start()


def stop_voice_detector():
    global voice_thread, stop_vd
    if voice_thread:
        stop_vd = True
        voice_thread.join()
        voice_thread = None


if __name__ == "__main__":
    listen()