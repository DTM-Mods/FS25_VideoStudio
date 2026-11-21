"""Records the game window (ffmpeg's gfxcapture: Windows Graphics Capture, works while other windows
cover it) into a master file, and the game's sound (the speakers, WASAPI loopback) into a WAV.

Every video frame is stamped with the wall clock (setpts=RTCTIME) and the sound's start is noted
the same way, so the cut lines them up exactly. The master is HEVC at a high quality on the
graphics card (NVENC, AMD AMF), else x264 on the processor.
"""
import json, os, subprocess, threading, time, wave, warnings

from vs_common import ffmpeg_exe, probe

GAME_EXE = r"(?i)FarmingSimulator2025Game\.exe"


def gpu_vendor():
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command",
                              "(Get-CimInstance Win32_VideoController).Name"], capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""
    low = out.lower()
    return "nvidia" if "nvidia" in low else "amd" if ("amd" in low or "radeon" in low) else "other"


def encoder_args(kind, qp=17):
    """(extra filter after the capture, encoder arguments) for the master."""
    if kind == "nvenc":
        return "", ["-c:v", "hevc_nvenc", "-preset", "p5", "-tune", "hq", "-rc", "constqp", "-qp", str(qp), "-g", "120", "-bf", "0"]
    if kind == "amf":
        return "", ["-c:v", "hevc_amf", "-quality", "quality", "-rc", "cqp", "-qp_i", str(qp), "-qp_p", str(qp), "-g", "120"]
    return ",hwdownload,format=bgra", ["-c:v", "libx264", "-preset", "ultrafast", "-crf", str(max(10, qp - 3)),
                                       "-pix_fmt", "yuv420p", "-g", "120"]


def capture_command(out, encoder="nvenc", fps=60, window_exe=GAME_EXE, qp=17):
    post, enc = encoder_args(encoder, qp)
    src = (f"gfxcapture=window_exe={window_exe}:max_framerate={fps}:capture_cursor=0,"
           f"setpts=RTCTIME/1000000/TB{post}")
    return [ffmpeg_exe(), "-hide_banner", "-loglevel", "warning", "-y", "-copyts", "-filter_complex", src] + enc + [out]


class AudioRecorder:
    """The speakers' sound into a 48 kHz 16-bit WAV, from a thread. .start_time: wall clock of the first sample."""
    RATE, CHANNELS, CHUNK = 48000, 2, 1200

    def __init__(self, path):
        self.path, self.start_time, self.error, self.frames = path, None, None, 0
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        try:
            import soundcard  # noqa: F401
        except ImportError:
            self.error = "no game sound: pip install --user soundcard"
            return False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return True

    def _run(self):
        import numpy as np
        import soundcard as sc
        warnings.filterwarnings("ignore", message=".*discontinuity.*")
        try:
            spk = sc.default_speaker()
            mic = sc.get_microphone(id=str(spk.name), include_loopback=True)
            with wave.open(self.path, "wb") as w, mic.recorder(samplerate=self.RATE, channels=self.CHANNELS) as rec:
                w.setnchannels(self.CHANNELS)
                w.setsampwidth(2)
                w.setframerate(self.RATE)
                while not self._stop.is_set():
                    data = rec.record(numframes=self.CHUNK)
                    if self.start_time is None:
                        # the chunk just returned ended now: its first sample is a chunk earlier
                        self.start_time = time.time() - len(data) / self.RATE
                    w.writeframes((np.clip(data, -1, 1) * 32767).astype("<i2").tobytes())
                    self.frames += len(data)
        except Exception as e:      # noqa: BLE001 - any audio device trouble: no sound, the video goes on
            self.error = f"game sound stopped: {e}"

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)


class Recorder:
    """recording/<stamp>/master.mkv (+ game.wav, recording.json)."""
    def __init__(self, folder, audio=True, encoder=None, fps=60, qp=17, window_exe=GAME_EXE, echo=print):
        os.makedirs(folder, exist_ok=True)
        self.folder, self.fps, self.qp, self.window_exe, self.echo = folder, fps, qp, window_exe, echo
        self.encoder = encoder or {"nvidia": "nvenc", "amd": "amf"}.get(gpu_vendor(), "x264")
        self.video = os.path.join(folder, "master.mkv")
        self.audio = AudioRecorder(os.path.join(folder, "game.wav")) if audio else None
        self.proc = None
        self.started_at = None

    def start(self):
        cmd = capture_command(self.video, self.encoder, self.fps, self.window_exe, self.qp)
        self.started_at = time.time()
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        if self.audio is not None and not self.audio.start():
            self.echo("! " + self.audio.error)
            self.audio = None
        time.sleep(2)
        if self.proc.poll() is not None:
            err = self.proc.stderr.read().decode("utf-8", "replace")
            raise RuntimeError("The recording didn't start:\n" + err[-2000:])
        self.echo(f"Recording the game window ({self.encoder}{', with the game sound' if self.audio else ''}) to {self.video}")
        return True

    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def stop(self):
        if self.proc is None:
            return None
        if self.proc.poll() is None:
            try:
                self.proc.stdin.write(b"q")
                self.proc.stdin.flush()
            except OSError:
                pass
            try:
                self.proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        err = self.proc.stderr.read().decode("utf-8", "replace").strip()
        if self.audio is not None:
            self.audio.stop()
        meta = {"video": "master.mkv", "encoder": self.encoder, "fps": self.fps, "started": self.started_at,
                "stopped": time.time()}
        if os.path.isfile(self.video) and os.path.getsize(self.video) > 0:
            info = probe(self.video)
            # the timestamps are the wall clock: the length is the end less the start
            seconds = info["duration"] - info["start"] if info["duration"] > 1e8 else info["duration"]
            meta.update(video_start=info["start"], width=info.get("width"), height=info.get("height"), seconds=seconds)
        if self.audio is not None and self.audio.start_time is not None and os.path.isfile(self.audio.path):
            meta.update(audio="game.wav", audio_start=self.audio.start_time, audio_seconds=self.audio.frames / AudioRecorder.RATE)
        if self.audio is not None and self.audio.error:
            meta["audio_error"] = self.audio.error
        if err:
            meta["ffmpeg"] = err[-1500:]
        with open(os.path.join(self.folder, "recording.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
        return meta
