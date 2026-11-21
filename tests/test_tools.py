"""Fast offline tests of the tools' logic (no game, no ffmpeg): reading the cards, pairing START/END,
the window size in game.xml, the log, the plans, chapters.

    python tests/test_tools.py
"""
import os, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import vs_cut, vs_game, vs_edit, fs25_video  # noqa: E402

failures = []
def check(cond, msg):
    print(('ok   ' if cond else 'FAIL ') + msg)
    if not cond:
        failures.append(msg)

W, H = vs_cut.SW, vs_cut.SH


def card(kind, code, blend=None):
    top = (255, 0, 255) if kind == "start" else (0, 255, 255)
    px = []
    for y in range(H):
        for x in range(W):
            if y >= int(H * 0.75):
                bit = (code >> (7 - x // (W // 8))) & 1
                c = (255, 255, 255) if bit else (0, 0, 0)
            else:
                c = top
            if blend:
                c = tuple(int(a * (1 - blend) + b * blend) for a, b in zip(c, (90, 120, 60)))
            px += c
    return bytes(px)


def scene():
    return bytes([(x * 7 + y * 13 + k * 50) % 256 for y in range(H) for x in range(W) for k in range(3)])


# ---------------------------------------------------------------- cards
check(vs_cut.classify(card("start", 1)) == ("start", 1), "START card, clip 1")
check(vs_cut.classify(card("end", 200)) == ("end", 200), "END card, clip 200")
check(vs_cut.classify(card("start", 0b10110011)) == ("start", 0b10110011), "bits read left to right")
check(vs_cut.classify(scene()) == (None, None), "a game picture is no card")
check(vs_cut.classify(card("start", 5, blend=0.5)) == (None, None), "a half-blended card (frame generation, TAA) is no card")
# a card with the HUD's notification box and hint text drawn over it (menu clips have the HUD on)
over = bytearray(card("start", 9))
for y in range(1, 4):
    for x in range(22, 31):
        i = (y * W + x) * 3
        over[i:i + 3] = bytes([60, 60, 70])
for x in range(10, 18):
    i = (8 * W + x) * 3
    over[i:i + 3] = bytes([230, 230, 230])
check(vs_cut.classify(bytes(over)) == ("start", 9), "a card with the HUD drawn over a corner of it")
grass = bytes([60, 140, 40] * (W * H))
check(vs_cut.classify(grass) == (None, None), "a flat green field is no card")

# ---------------------------------------------------------------- pairing
frames = [(i, None, None) for i in range(10)]
frames += [(10 + i, "start", 1) for i in range(90)]
frames += [(100 + i, None, None) for i in range(300)]
frames += [(400 + i, "end", 1) for i in range(27)]
frames += [(427 + i, "start", 2) for i in range(90)]
frames += [(517 + i, None, None) for i in range(200)]          # the game ended: no END for clip 2
runs = vs_cut.runs(frames)
check([r[:2] for r in runs] == [("start", 1), ("end", 1), ("start", 2)], "runs of cards")
clips = vs_cut.find_clips(runs, trim=2)
check(clips == [(1, 102, 397)], f"clip 1 between its cards, 2 frames trimmed each side; clip 2 without END left out ({clips})")
# a clip number used again later (255 wraps): each START pairs with the next END of its number
frames2 = [(i, "start", 3) for i in range(5)] + [(5 + i, None, None) for i in range(50)] + [(55 + i, "end", 3) for i in range(5)]
frames2 += [(60 + i, "start", 3) for i in range(5)] + [(65 + i, None, None) for i in range(40)] + [(105 + i, "end", 3) for i in range(5)]
check(len(vs_cut.find_clips(vs_cut.runs(frames2))) == 2, "the same number twice: two clips")
m = vs_cut.match([(1, 0, 10), (2, 20, 30), (1, 40, 50)], [{"code": 1, "shot": "a"}, {"code": 2, "shot": "b"}, {"code": 1, "shot": "c"}])
check([x[3]["shot"] for x in m] == ["a", "b", "c"], "clip list matched by number, in order")

# ---------------------------------------------------------------- game.xml
xml = os.path.join(tempfile.mkdtemp(), "game.xml")
with open(xml, "w", encoding="utf-8") as f:
    f.write("<game>\n    <display>\n        <width>5104</width>\n        <height>1401</height>\n"
            "        <fullscreenMode>windowed_fullscreen</fullscreenMode>\n        <previousWidth>1920</previousWidth>\n"
            "    </display>\n    <width>77</width>\n</game>\n")
before = vs_game.read_display(xml)
check(before == {"width": "5104", "height": "1401", "fullscreenMode": "windowed_fullscreen"}, "window settings read")
vs_game.write_display(xml, {"width": 1600, "height": 900, "fullscreenMode": "windowed"})
check(vs_game.read_display(xml) == {"width": "1600", "height": "900", "fullscreenMode": "windowed"}, "set to 1600x900 windowed")
text = open(xml, encoding="utf-8").read()
check("<width>77</width>" in text and "<previousWidth>1920</previousWidth>" in text, "nothing else in game.xml touched")
vs_game.write_display(xml, before)
check(vs_game.read_display(xml) == before, "and put back")

# ---------------------------------------------------------------- the log
w = vs_game.LogWatch()
w.feed("[VideoStudio] Loaded 0.1.0.0. Right Shift + 1 showcase\nAuto start local savegame\n")
w.feed("[VideoStudio] autorun: started, 5 steps, first in 12 s\n[VideoStudio] Clip 1 orbit (orbit dur=6): 6.0 s, Tiger, light golden\n")
w.feed("[VideoStudio] Clip 1 done: 6.02 s\n[VideoStudio] autorun: step 3/5 vsKeys ctrl+f tractor -> Keys\n")
w.feed("Error: something in another mod\n  call stack line\n[VideoStudio] autorun: done, 1 clip(s)\n")
check(w.loaded and w.autostart and w.started and w.done, "log: loaded, auto start, started, done")
check(w.clips == [(1, "orbit")] and w.clip_done == 1, "log: clips counted")
check(w.keys == ["ctrl+f tractor"] and w.errors == 1, "log: keys to type, errors counted")

# ---------------------------------------------------------------- plans
for name, steps in fs25_video.PLANS.items():
    check(steps[-1] == "quit" and name in fs25_video.PLAN_TEXT, f"plan {name} ends with quit and is explained")
steps = fs25_video.with_options(fs25_video.with_light(fs25_video.with_target(fs25_video.PLANS["showcase"], "Tiger"), "morning"), 35, "FS25_X")
check(steps[0] == "vsTarget Tiger" and "vsLight morning" in steps and "vsLight off" in steps, "target first, light swapped, off kept")
check(steps[2:4] == ["vsFov 35", "vsFolder FS25_X"], "fov and folder right after getting in")

# a how-to remade from older clips: only the shots its steps film; the thumbnail is its own screen
how = {"kind": "script", "steps": ["vsLight golden", "vsShot ui dur=8 keys=lalt+m at=1.5", "vsShot ui dur=5"],
       "thumbnail": {"text": "Where does the money go?"}}
sb = {"sections": [{"clip": "01_orbit.mov", "title": True}, {"clip": "02_ui.mov"}, {"clip": "03_ui.mov"}],
      "thumbnail": {"clip": "01_orbit.mov", "at": 0.85}, "hook": {"clip": "01_orbit.mov"}}
sb = fs25_video.apply_mod_plan(sb, how)
check([s["clip"] for s in sb["sections"]] == ["02_ui.mov", "03_ui.mov"] and sb["sections"][0].get("title"),
      "how-to: a shot its steps don't film is left out, the title moves on")
check(sb["thumbnail"]["clip"] == "02_ui.mov" and sb["hook"] is None, "how-to: thumbnail from its first screen, no hook")
sb = {"sections": [{"clip": "01_orbit.mov"}, {"clip": "02_ui.mov"}, {"clip": "03_ui.mov"}],
      "thumbnail": {"clip": "01_orbit.mov", "at": 0.85}, "hook": None}
sb = fs25_video.apply_mod_plan(sb, dict(how, steps=how["steps"] + ["vsShot orbit"], thumbnail={"shot": "ui#2"}))
check(sb["thumbnail"]["clip"] == "03_ui.mov" and "shot" not in sb["thumbnail"], "the plan can name the thumbnail's shot")

# a how-to keeps the order it was filmed in; the end card on the last clip
sb = {"sections": [{"clip": "02_static.mov"}, {"clip": "05_crane.mov", "end_card": True}, {"clip": "01_pov.mov"},
                   {"clip": "03_pov.mov"}], "thumbnail": {"clip": "02_static.mov"}, "hook": None}
sb = fs25_video.apply_mod_plan(sb, {"kind": "script", "steps": ["vsShot pov", "vsShot static", "vsShot crane"]})
check([s["clip"] for s in sb["sections"]] == ["01_pov.mov", "02_static.mov", "03_pov.mov", "05_crane.mov"]
      and sb["sections"][0].get("title") and sb["sections"][-1].get("end_card")
      and not any(s.get("end_card") for s in sb["sections"][:-1]), "how-to: clips in filmed order, title first, end card last")

# one game session for several mods: steps one after the other, clips sorted back to each mod
pa = {"mod": "FS25_A", "steps": ["vsShot ui dur=5"]}
pb = {"mod": "FS25_B", "target": "Tiger", "move": "tree", "steps": ["vsEnter", "vsShot pov dur=5"]}
steps = fs25_video.batch_steps([pa, pb])
check(steps[:2] == ["vsFolder FS25_A", "vsShot ui dur=5"] and "vsMenu close" in steps
      and steps.index("vsMenu close") < steps.index("vsFolder FS25_B") < steps.index("vsMove tree") < steps.index("vsShot pov dur=5")
      and steps[-1] == "vsMove back", f"batch steps: each mod's own, a menu closed between ({steps})")
import tempfile, shutil, json  # noqa: E402
tmp = tempfile.mkdtemp()
src = os.path.join(tmp, "clips")
os.makedirs(src)
lists = {m: os.path.join("modSettings", "FS25_VideoStudio", m, "_clips_1.xml") for m in ("FS25_A", "FS25_B")}
clips = [{"file": "01_ui.mov", "run": {"list": lists["FS25_A"]}}, {"file": "02_pov.mov", "run": {"list": lists["FS25_B"]}},
         {"file": "03_pov.mov", "run": {"list": lists["FS25_B"]}}]
for c in clips:
    open(os.path.join(src, c["file"]), "w").close()
json.dump({"fps": 60, "clips": clips}, open(os.path.join(src, "clips.json"), "w"))
old_videos, fs25_video.VIDEOS = fs25_video.VIDEOS, tmp
parts = fs25_video.split_clips(src, [pa, pb, {"mod": "FS25_C"}], "S")
fs25_video.VIDEOS = old_videos
got = {m: [c["file"] for c in json.load(open(os.path.join(d, "clips.json")))["clips"]] for m, d in parts.items()}
check(got == {"FS25_A": ["01_ui.mov"], "FS25_B": ["02_pov.mov", "03_pov.mov"]}
      and os.path.isfile(os.path.join(tmp, "S_FS25_B", "clips", "03_pov.mov")), f"batch clips sorted by mod, none for C ({got})")
shutil.rmtree(tmp, ignore_errors=True)

# ---------------------------------------------------------------- chapters
segs = [{"kind": "hook", "seconds": 4}, {"kind": "intro", "seconds": 5}, {"kind": "section", "chapter": "Overview", "seconds": 60},
        {"kind": "section", "seconds": 10}, {"kind": "section", "chapter": "Colors", "seconds": 24},
        {"kind": "section", "chapter": "At work", "seconds": 4}, {"kind": "outro", "seconds": 20}]
starts = [0, 3.4, 7.8, 67.2, 76.6, 100, 103.2]
ch = vs_edit.chapters_of(segs, starts, {}, 123.2)
check(ch is not None and ch[0] == ("00:00", "Intro") and ("01:16", "Colors") in ch, f"chapters from 00:00 ({ch})")
check(all(n != "At work" for _, n in ch), "a chapter under 10 s is left out")
check(vs_edit.chapters_of(segs[:3], starts[:3], {}, 40) is None, "too short for 3 chapters: none")

print()
if failures:
    print(f"{len(failures)} FAILED")
    sys.exit(1)
print("all ok")
