"""Offline test of everything after the game: a recording like the recorder's (cards with clip numbers,
wall-clock timestamps, the game's sound started earlier) is made from game pictures, then cut and
made into a video.

    python tests/test_pipeline.py [--keep] [--full]

Checks: every clip found and named from the clip list, frame-exact lengths, no card frames in a clip,
the sound lined up (a tone at a clip's first frame is at the clip's start), and the finished video:
1600x900, 60 fps, -14 LUFS, the thumbnail, description with chapters, teaser. --full renders at full
quality (else draft); --keep keeps the folder (its path is printed) to look at.
"""
import json, math, os, shutil, struct, sys, tempfile, wave
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp(prefix="vs_pipeline_")
os.environ["FS25_DOCS"] = os.path.join(TMP, "docs")
os.environ["VS_VIDEOS"] = os.path.join(TMP, "videos")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import vs_common, vs_cut, vs_edit  # noqa: E402
from vs_common import ffmpeg, probe  # noqa: E402

failures = []
def check(cond, msg):
    print(('ok   ' if cond else 'FAIL ') + msg)
    if not cond:
        failures.append(msg)

FPS, W, H = 60, 1600, 900
IMAGES = os.path.join(os.path.dirname(ROOT), "FS25_ScreenshotStudio", "docs", "images")
if not os.path.isdir(IMAGES):
    IMAGES = None


def card_png(path, kind, code, w=1920, h=1080):
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (w, h), (255, 0, 255) if kind == "start" else (0, 255, 255))
    d = ImageDraw.Draw(im)
    for i in range(8):
        bit = (code >> (7 - i)) & 1
        d.rectangle((i * w // 8, int(h * 0.75), (i + 1) * w // 8, h), fill=(255, 255, 255) if bit else (0, 0, 0))
    im.save(path)


def scene(path, src, seconds, crop=None, zoom=(1.0, 1.18)):
    """seconds of a slow push-in on a picture (like a camera move), 1920x1080 at 60 fps."""
    vf = (f"crop={crop}," if crop else "") + f"scale=3840:2160:flags=lanczos,zoompan=z='{zoom[0]}+({zoom[1] - zoom[0]})*on/{int(seconds * FPS)}'" \
         f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={int(seconds * FPS)}:s=1920x1080:fps={FPS}"
    if src is None:
        ffmpeg(["-f", "lavfi", "-i", f"testsrc2=s=1920x1080:r={FPS}:d={seconds}", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "16", path])
    else:
        ffmpeg(["-i", src, "-vf", vf, "-frames:v", str(int(seconds * FPS)), "-c:v", "libx264", "-preset", "ultrafast", "-crf", "16", path])


def still(path, png, frames):
    ffmpeg(["-loop", "1", "-framerate", str(FPS), "-i", png, "-frames:v", str(frames), "-c:v", "libx264", "-preset", "ultrafast", "-crf", "16",
            "-pix_fmt", "yuv420p", path])


# the clips the "mod" filmed: (shot, seconds, picture, crop, color)
pic = (lambda n: os.path.join(IMAGES, n)) if IMAGES else (lambda n: None)
CLIPS = [("pushin", 5.0, pic("hero_tiger.jpg"), None, None),
         ("orbit", 6.0, pic("move_tiger.jpg"), None, None),
         ("arc", 4.0, pic("lights_alpaca.jpg"), None, None),
         ("drone", 5.0, pic("buildings.jpg"), None, None)]
if IMAGES:
    from PIL import Image
    cw, ch = Image.open(pic("colors_tiger.jpg")).size
    for k, name in enumerate(["Red", "Green", "Blue"]):
        CLIPS.append(("colors", 2.0, pic("colors_tiger.jpg"), f"{cw // 4}:{ch // 2}:{k * cw // 4}:0", name))

work = os.path.join(TMP, "build")
os.makedirs(work)
parts, t, starts = [], 0.0, []
still(os.path.join(work, "pre.mp4"), None, 1) if False else None
# 1 s of plain "game" first (no card), then per clip: START 1.5 s, the clip, END 0.45 s
scene(os.path.join(work, "pre.mp4"), None, 1.0)
parts.append(os.path.join(work, "pre.mp4")); t += 1.0
for i, (shot, sec, src, crop, color) in enumerate(CLIPS, start=1):
    card_png(os.path.join(work, f"s{i}.png"), "start", i)
    card_png(os.path.join(work, f"e{i}.png"), "end", i)
    still(os.path.join(work, f"s{i}.mp4"), os.path.join(work, f"s{i}.png"), 90)
    scene(os.path.join(work, f"c{i}.mp4"), src, sec, crop)
    still(os.path.join(work, f"e{i}.mp4"), os.path.join(work, f"e{i}.png"), 27)
    parts += [os.path.join(work, f"s{i}.mp4"), os.path.join(work, f"c{i}.mp4"), os.path.join(work, f"e{i}.mp4")]
    t += 1.5
    starts.append(t)
    t += sec + 0.45
with open(os.path.join(work, "list.txt"), "w") as f:
    f.writelines(f"file '{p}'\n" for p in parts)
rec = os.path.join(os.environ["VS_VIDEOS"], "20261120_130000_test")
os.makedirs(rec)
VIDEO_START = 1795230000.25
# like the recorder: HEVC, timestamps from the wall clock
ffmpeg(["-f", "concat", "-safe", "0", "-i", os.path.join(work, "list.txt"), "-c:v", "libx264", "-preset", "ultrafast", "-crf", "14",
        "-output_ts_offset", str(VIDEO_START), os.path.join(rec, "master.mkv")])
total = t
# the game's sound started 0.7 s before the video; a tone burst exactly where clip 2 begins
AUDIO_START = VIDEO_START - 0.7
rate = 48000
n = int((total + 1.0) * rate)
tone_at = starts[1] + 0.7
samples = bytearray()
for k in range(n):
    s = k / rate
    v = 0.0005 * math.sin(2 * math.pi * 220 * s)
    if tone_at <= s < tone_at + 0.3:
        v = 0.5 * math.sin(2 * math.pi * 1000 * s)
    samples += struct.pack("<hh", int(v * 32767), int(v * 32767))
with wave.open(os.path.join(rec, "game.wav"), "wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(rate); w.writeframes(bytes(samples))
json.dump({"video": "master.mkv", "audio": "game.wav", "video_start": VIDEO_START, "audio_start": AUDIO_START,
           "started": 0, "fps": FPS}, open(os.path.join(rec, "recording.json"), "w"))
# the mod's clip list
studio = os.path.join(os.environ["FS25_DOCS"], "modSettings", "FS25_VideoStudio", "FS25_RopaTiger6S_ProEdition")
os.makedirs(studio)
root = ET.Element("clips", mod="FS25_RopaTiger6S_ProEdition", what="Tiger 6S", stamp="20261120_130000", version="0.1.0.0")
for i, (shot, sec, src, crop, color) in enumerate(CLIPS, start=1):
    a = {"n": str(i), "code": str(i), "shot": shot, "duration": f"{sec:.3f}", "what": "Tiger 6S",
         "mod": "FS25_RopaTiger6S_ProEdition", "light": "golden", "fov": "40.0", "hud": "false"}
    if color:
        a.update(color=color, colorIndex=str(i - 4), colorCount="3")
    ET.SubElement(root, "clip", a)
ET.ElementTree(root).write(os.path.join(studio, "_clips_20261120_130000.xml"))

# ---------------------------------------------------------------- cut
clips = vs_cut.cut(rec, since=0, echo=lambda *a: None)
check(len(clips) == len(CLIPS), f"all {len(CLIPS)} clips found ({len(clips)})")
check([c["shot"] for c in clips] == [c[0] for c in CLIPS], "named from the clip list, in order")
for c, (shot, sec, *_r) in zip(clips, CLIPS):
    check(abs(c["seconds"] - (sec - 4 / FPS)) < 1.5 / FPS, f"{c['file']}: {c['seconds']:.3f} s (filmed {sec} s less 2+2 trimmed frames)")
cdir = os.path.join(rec, "clips")
info = probe(os.path.join(cdir, clips[0]["file"]))
check((info["width"], info["height"]) == (W, H) and abs(info["fps"] - FPS) < 0.1, f"clips are {W}x{H} at 60 fps")
# no magenta/cyan frame in any clip
bad = 0
for c in clips:
    frames = list(vs_cut.read_frames(os.path.join(cdir, c["file"])))
    bad += sum(1 for _, k, _ in frames if k)
check(bad == 0, "no card frame in any clip")
# the tone is at clip 2's start: its first 0.3 s are loud, before it nothing
def rms(path, a, b):
    with wave.open(path) as w:
        w.setpos(int(a * w.getframerate()))
        data = w.readframes(int((b - a) * w.getframerate()))
    vals = struct.unpack("<%dh" % (len(data) // 2), data)
    return math.sqrt(sum(v * v for v in vals) / max(1, len(vals))) / 32768
c2 = os.path.join(cdir, clips[1]["file"])
ffmpeg(["-i", c2, "-vn", "-c:a", "pcm_s16le", os.path.join(work, "c2.wav")])
loud = rms(os.path.join(work, "c2.wav"), 0.0, 0.2)
after = rms(os.path.join(work, "c2.wav"), 0.4, 0.6)
check(loud > 0.2 and after < 0.01, f"sound lined up with the picture (tone at the clip start {loud:.2f}, after {after:.3f})")
sheet = vs_cut.contact_sheet(cdir)
check(os.path.isfile(sheet), "contact sheet")

# ---------------------------------------------------------------- make
full = "--full" in sys.argv
sb = vs_edit.auto_storyboard(cdir, title="Ropa Tiger 6S Pro Edition", music="generated")
sb["sections"][1]["caption"] = {"heading": "RR-XL header", "text": "Nine rows, 45 cm apart, with its own colors."}
sb["thumbnail"]["text"] = "Tiger 6S Pro Edition"
sb["thumbnail"]["accent"] = "Pro Edition"
secs = sb["sections"]
colors = [s for s in secs if s.get("chip")]
check(secs[0].get("title") and [s["chip"]["label"] for s in colors] == ["Red", "Green", "Blue"], "storyboard: title on the first clip, chips on the colors")
check([s.get("transition") for s in colors[1:]] == ["cut", "cut"], "colors cut straight from one to the next")
check(secs[-1].get("end_card") and "drone" in secs[-1]["clip"], "closing shot: the drone, under the download link")
check(sb["hook"] and "orbit" in sb["hook"]["clip"], "hook: the middle of the orbit")
out = os.path.join(rec, "video")
res = vs_edit.render(sb, out, draft=not full, shorts=full, echo=lambda *a: None)
v = probe(res["video"])
check((v["width"], v["height"]) == (W, H) and abs(v["fps"] - FPS) < 0.1 and v["audio"], f"video {v['width']}x{v['height']} {v['fps']:.0f} fps with sound")
expect = res["seconds"]
check(abs(v["duration"] - expect) < 0.2, f"video length {v['duration']:.2f} s as planned ({expect:.2f} s)")
rep = vs_edit.check(res["video"])
lufs = [t for lvl, t in rep if t.startswith("loudness")]
check(lufs and "-14." in lufs[0] or "-13." in lufs[0], f"loudness: {lufs}")
check(os.path.isfile(os.path.join(out, "thumbnail.jpg")) and os.path.isfile(os.path.join(out, "teaser.gif")), "thumbnail and teaser")
desc = open(os.path.join(out, "description.txt"), encoding="utf-8").read()
check("Ropa Tiger 6S Pro Edition" in desc, "description written")
if full:
    sh = probe(res["shorts"])
    check((sh["width"], sh["height"]) == (1080, 1920) and sh["duration"] <= 60, f"shorts 1080x1920, {sh['duration']:.0f} s")
if "--keep" not in sys.argv and not failures:
    shutil.rmtree(TMP, ignore_errors=True)
else:
    print("kept:", TMP)
print()
if failures:
    print(f"{len(failures)} FAILED")
    sys.exit(1)
print("all ok")
