# Patch notes

## 0.1.0.25

- Filming by hand: a step window beside the game window (never in the video) shows and says each step and
  waits for you: say "next", "go" or "done" or press Right Shift + 9; "pause" / Right Shift + 8, "go on".
  A bar shows the whole set: which mod, how far, about how long. The clip ends after your last step, and the
  video is cut where you really went on (plans: `"hand"` steps, `vsShot ui dur=0 max=900 hand=1`).
- `vsUnfold [fold]`: the machine unfolded the way it works (or folded again), also during a clip
  (`run=vsUnfold`); color copies stay unfolded like the original, or alternate open and closed
  (`vsShot colors fold=alt`).
- `vsSave`: the game saves while you play (what a mod shows during a save can be filmed).
- `vsMove` only picks a place the camera sees from every side (a shed next to it hid a roller).
- Clip options: `keep=` (another mod's HUD stays in a menu clip), `help=0` (the F1 box hidden),
  `max=` (an open clip's longest length).
- Editor: `zoom` on a section (a small HUD filling the frame); the cutter pads the sound when it ends early.
- The runner switches Video Studio on for the run in a savegame that doesn't have it (put back afterwards).
- Trailers: `python tools/make_trailer.py trailers/<spec>.json [--sheet]` cuts the best moments of many mods'
  videos into one (the DTM Mods channel trailer is `trailers/dtm_channel.json`); each shot carries its mod's
  name; `--sheet` shows the chosen moments first. The brand outro can be shortened (`outro_seconds`).

## 0.1.0.0 (not released yet)

First version.

- The mod: 20 camera moves (orbit, hero arc, push in, reveal, crane, drone, top-down, head-on, rear, fly-by,
  detail pass, locked-off, time-lapse, chase, alongside, lead, drive-past, your own camera, menus, every color),
  framing that keeps the whole machine in the picture, moves that go round things in the way, six light presets,
  weather, vehicle lights, driving and working for footage of a machine at work, START/END cards with the clip
  number, a clip list per run, an autorun for the runner.
- The tools: the runner (game, window size, savegame backup, recording), the recorder (window and game sound,
  lined up by the wall clock), the cutter (finds the cards, frame-exact), the editor (title, captions, color chips,
  transitions, grades, letterbox, hook, brand intro and outro, watermark, music, -14 LUFS, thumbnail,
  description with chapters, teaser, Shorts) and a music generator.
