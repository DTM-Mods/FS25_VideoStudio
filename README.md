<p align="center">
  <a href="https://github.com/DTM-Mods"><img src="https://raw.githubusercontent.com/DTM-Mods/.github/main/assets/dtm-header.jpg" alt="DTM Mods by PropaineX & Fennell" width="100%"></a>
</p>

<p align="center">
  <img src="icon_videoStudio.png" alt="DTM Video Studio icon" width="128">
</p>

<h1 align="center">DTM Video Studio</h1>

<p align="center">
  <img src="https://img.shields.io/badge/Farming%20Simulator-25-2E6B4F" alt="Farming Simulator 25">
  <a href="https://github.com/DTM-Mods/FS25_VideoStudio/releases/latest"><img src="https://img.shields.io/github/v/release/DTM-Mods/FS25_VideoStudio?label=version&color=D9A441" alt="Latest version"></a>
  <a href="https://github.com/DTM-Mods"><img src="https://img.shields.io/badge/DTM-Mods-143326" alt="DTM Mods"></a>
</p>

<p align="center">
  <b>The game films your mod. The tools make the video.</b><br>
  <sub>by Fennell</sub>
</p>

A tool for modders: cinematic camera moves around your mod, played by Farming Simulator 25 itself, recorded
and cut by the tools, and made into a finished video for YouTube, your website and wherever else: title,
captions, a chip per color, transitions, music, your intro and outro, thumbnail, description with chapters,
a teaser loop and a Shorts version. **Single player only** (the mod switches itself off in multiplayer); it
never goes on a server or the ModHub. The sister of [DTM Screenshot Studio](https://github.com/DTM-Mods/FS25_ScreenshotStudio).

**Download** (the [releases](https://github.com/DTM-Mods/FS25_VideoStudio/releases)): `FS25_VideoStudio.zip`
is the mod, into `Documents/My Games/FarmingSimulator2025/mods` as it is. `VideoStudio_Tools.zip` is the rest:
unzip it anywhere. The tools need **Python 3** (`pip install pillow numpy soundcard`, the tests also `lupa`) and
**ffmpeg** 7 or newer with `gfxcapture` (`winget install Gyan.FFmpeg`). Windows 10/11.

## One command

```
tools\film.cmd 1 --plan showcase --target "Tiger" --make
```

starts the game with savegame 1, films the Tiger in golden hour (push in, orbit, reveal, hero arc, crane,
fly-by, rear, drone, every color), ends the game without saving, cuts the clips and makes the video. You get,
in `<your user folder>\FS25 Video Studio\<time>_showcase\`:

| | |
|-|-|
| `video\<title>_1600x900.mp4` | the video: H.264 High, 60 fps, AAC 320k, loudness -14 LUFS (what YouTube plays at), fast start for the web |
| `video\thumbnail.jpg` | 1280x720, the brand overlay and three to five words |
| `video\description.txt` | title ideas, the description with the download link, version and **chapters**, tags |
| `video\teaser.mp4`, `teaser.gif` | an 8 s loop for the README and the website |
| `video\shorts.mp4` | 1080x1920 for YouTube Shorts (with `--shorts`) |
| `video\storyboard.json` | what went where: edit it and `make --storyboard` it again |
| `clips\` | every clip on its own, 1600x900 60 fps, with the game's sound; `_sheet.jpg` shows them |
| `master.mkv`, `game.wav` | the raw recording (a few GB: delete it when the video is done) |

That folder is outside Documents and Videos on purpose: OneDrive often syncs those, and a master is big.
`VS_VIDEOS` puts it elsewhere.

## In the game

| Key | What it does |
|-----|--------------|
| **Right Shift + 1** | **Showcase**: a set of camera moves around what you sit in (with everything attached), the target, or the nearest building |
| **Right Shift + 2** | **Orbit**: one slow 360 degree orbit |
| **Right Shift + 3** | **Follow**: a chase camera while you drive; again to stop |
| **Right Shift + 4** | **Light**: golden hour, morning mist, midday, overcast, dawn, night (lights on); then the old time back |
| **Right Shift + 0** | **Stop**: ends the clip now and clears the queue |

The keys can be changed in Options > Controls. To film by hand: `tools\record.cmd` (records the game window while
you play), press the keys or use the console, Enter in the window to stop; it cuts the clips.

### The shots

`vsShot <shot> [options]`, e.g. `vsShot orbit dur=20 deg=180 elev=8`. `vsShots` lists them in the log.

| Shot | | Shot | |
|------|-|------|-|
| `orbit` | slow 360 degrees round it | `follow` | chase camera behind a moving machine |
| `arc` | low hero arc at the front corner | `side` | alongside a moving machine |
| `pushin` | pushes in to the framed view | `lead` | in front, looking back at it as it comes |
| `pullback` | from a close detail back to all of it | `flypast` | a tripod ahead on the ground: it drives past |
| `crane` | rises from the ground and looks down | `static` | a locked-off view |
| `drone` | high and wide, turning | `timelapse` | locked-off while the day goes by (`from=6 to=21`) |
| `topdown` | from straight above | `colors` | every shop color; the camera carries on round between them |
| `front` | head-on, low, pushing in | `pov` | your own camera (cab, outside), no HUD |
| `rear` | an arc round the back | `ui` | the screen as it is, menus and HUD (`vsMenu` opens one) |
| `flyby`, `pass` | along its side, wide or close | | |

Options: `dur=` seconds (`dur=0`: until `vsStop`), `ease=` linear/sine/inout/out/in/smooth, `fov=`, `angle=` (start, 0 = front,
90 = its left), `deg=` how far it turns, `dir=-1`, `elev=`, `dist=` (1 = the whole machine fills the picture),
`height=`, `side=left|right`, and the raw pose `a0= a1= e0= e1= d0= d1= lz0= fov1=` ...; colors `max= config=`.

**Framing.** The camera knows how big the machine is (its size box, unfolded work areas, every part) and keeps all
of it in the picture, at one distance for a whole orbit so it doesn't breathe in and out. **Something in the way**
(a wall, a pole, a tree's crown, another car) is found with rays before the clip starts; the move is then mirrored,
raised or taken from further round. On foot, your own character is hidden while filming.

**Machines that move.** `vsWork on` unfolds, lowers and switches on what is hitched (the way the game's helper
starts work), `vsDrive 9` drives straight on with cruise control; then `follow`, `side`, `lead`, `flypast`.
The `work` plan does all of that: park it at the start of a field, facing along it.

Other console commands: `vsShowcase [vehicle|quick|building|work]`, `vsLight`, `vsWeather sun|cloudy|rain|snow`,
`vsVehicleLights on|off|beacon|all`, `vsTarget <name>` / `vsList` / `vsEnter` (as in Screenshot Studio),
`vsMenu`, `vsFolder`, `vsFov`, `vsQuiet` (hides other mods' drawing: Courseplay, AutoDrive, hints), `vsClear`, `vsRadius`.

## How the recording works

The game can't record video, so the tools record its window with ffmpeg's `gfxcapture` (Windows Graphics
Capture: it works while other windows cover the game) on the graphics card (NVENC, AMD AMF, else x264), and the
game's sound from the speakers (WASAPI loopback). Every frame carries the wall-clock time, and so does the sound,
so they line up exactly.

The mod marks each clip: while the camera gets into place and the textures stream in, it covers the screen
with a **START card** (magenta), then the camera moves, then an **END card** (cyan). Both carry the clip number
as eight black and white cells along the bottom. The cutter reads the recording frame by frame, finds the cards,
and takes exactly the frames between them, so log timing never matters and nothing of the card gets into a clip.
The mod's `_clips_<time>.xml` (in `modSettings/FS25_VideoStudio/<mod>/`) says what each clip is.

For the run the game window is set to `--window` (1600x900) in `game.xml`, windowed; your own settings go back
afterwards. A bigger window (`--window 2240x1260`) is scaled down to 1600x900: sharper.

## Making the video

```
python tools/fs25_video.py make "<recording>\clips" --style cinematic --shorts
python tools/fs25_video.py storyboard "<recording>\clips"      writes storyboard.json to edit
python tools/fs25_video.py make "<recording>\clips" --storyboard "<recording>\clips\storyboard.json"
```

| Style | |
|-------|-|
| `showcase` | natural color, dissolves, a 4 s hook before the intro |
| `cinematic` | film look (soft contrast, warm highlights, vignette), 2:1 letterbox, slower dissolves |
| `clean` | no hook, short dissolves |
| `punchy` | vivid, quick slides |

The **storyboard** is plain JSON: the title, the line under it, the hook, the order of the clips, each one's trim,
speed, transition (`fade`, `cut`, `fadeblack`, any of ffmpeg's `xfade` ones), its caption
(`{"heading": "RR-XL header", "text": "Nine rows, 45 cm apart."}`), the chapter it starts, the music, the game
sound's level (`game_audio`), the grade (`natural`, `warm`, `vivid`, `film`, `none`), the letterbox, the end card
and the thumbnail's words.

**Music.** `--music generated` (the default) makes a calm track here from nothing but numbers: nobody else's
recording, so no copyright claim; `--seed 2` another one. For a real upload, music from YouTube's Audio Library is
better: `--music track.mp3` (it loops and fades to the video's length). The game's own sound plays under it.

**Brand.** `--brand dtm` uses DTM Mods' kit when it sits next to the repo (`_brand/`: Outfit font, colors, the
intro, the outro with YouTube's end screen, the watermark, the thumbnail overlay); `--brand neutral` has no logos;
your own is a JSON file like `presets/brand_dtm.json`.

`python tools/fs25_video.py check <video>` checks size, frame rate, loudness, and black or frozen stretches.

## Running it

`fs25_video.py run <save> [--plan ...] [--target <name>] [--light ...] [--fov ...] [--window WxH] [--no-audio]
[--make ...]`, or `tools\film.cmd`. `saves` lists your savegames, `plans` the plans:

| Plan | |
|------|-|
| `showcase` | golden hour: the vehicle showcase, then every color |
| `quick` | golden hour: push in, orbit, hero arc, drone |
| `colors` | every color at midday |
| `building` | a building: drone, orbit, push in, crane, fly-by, top-down, a day as a time-lapse |
| `work` | lowered and working, driving straight on: chase, alongside, lead, drive-past |
| `lights` | dawn, mist, midday, golden hour, night |
| `full` | showcase, colors, mist, a night orbit with the lights on |
| `smoke` | a quick test of the whole chain |

Set the save up once: install the mod zip yourself (the script never copies it into the mods folder), switch it
on in a single-player save, park the machine somewhere nice, stand next to it, save. The runner checks the game
isn't running and that the installed zip is this version, backs the savegame up (and puts it back if the game
autosaved), presses START, records, and ends the game without saving.

`--steps "vsEnter" "vsShot orbit dur=20"` runs your own steps; `wait <s>` and `vsKeys <keys>` (the runner types
them, e.g. `ctrl+f tractor enter`) work too.

**Keep it light while you play.** The editing is heavy work for the processor (x264's best quality). Every
ffmpeg the tools start runs at low priority, and while the game is running with half the threads, but it is
still best not to `make` a video while you play on the same computer.

## Files

| | |
|-|-|
| `scripts/VideoStudio.lua` | the mod: shots, framing, cards, colors, lights, driving, autorun |
| `tools/fs25_video.py` | the command line: `run`, `record`, `cut`, `make`, `storyboard`, `check`, `music`, `list` |
| `tools/vs_record.py`, `vs_cut.py`, `vs_edit.py`, `vs_music.py`, `vs_game.py` | recording, cutting, editing, music, the game |
| `tools/*.cmd` | double-click shortcuts: `film`, `record`, `make`, `test` |
| `presets/brand_*.json` | brands |
| `tests/` | `test_video_studio.py` (the mod, with the engine stubbed in Lua), `test_tools.py` (fast), `test_pipeline.py` (the whole edit from a made-up recording: heavy) |

## License

MIT, see [LICENSE.txt](LICENSE.txt).

---

<p align="center">
  <a href="https://github.com/DTM-Mods"><img src="https://raw.githubusercontent.com/DTM-Mods/.github/main/assets/dtm-intro.gif" alt="DTM Mods by PropaineX & Fennell" width="420"></a><br>
  <sub>Part of <a href="https://github.com/DTM-Mods">DTM Mods</a> (Designed To Manage) by PropaineX & Fennell</sub><br><br>
  <a href="https://ko-fi.com/dtmmods"><img src="https://img.shields.io/badge/Ko--fi-support%20DTM%20Mods-1F4D3A?logo=kofi&logoColor=F4F1E8" alt="Support DTM Mods on Ko-fi"></a>
  <a href="https://www.paypal.com/donate/?business=dtmmods%40gmail.com&amp;no_recurring=0&amp;item_name=DTM+Mods&amp;currency_code=USD"><img src="https://img.shields.io/badge/PayPal-donate-1F4D3A?logo=paypal&logoColor=F4F1E8" alt="Donate to DTM Mods with PayPal"></a><br>
  <a href="https://www.youtube.com/@DTMMods"><img src="https://img.shields.io/badge/YouTube-videos-1F4D3A?logo=youtube&logoColor=F4F1E8" alt="DTM Mods on YouTube"></a>
  <a href="https://dtmmods.itch.io"><img src="https://img.shields.io/badge/itch.io-our%20mods-1F4D3A?logo=itchdotio&logoColor=F4F1E8" alt="DTM Mods on itch.io"></a>
  <a href="https://www.kingmods.net/en/profile/dtmmods"><img src="https://img.shields.io/badge/KingMods-our%20mods-1F4D3A" alt="DTM Mods on KingMods"></a>
</p>
