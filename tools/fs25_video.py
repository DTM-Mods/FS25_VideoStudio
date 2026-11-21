"""DTM Video Studio: films a mod in Farming Simulator 25 and makes the finished video.

    python fs25_video.py saves                                  your savegames, and which have the mod
    python fs25_video.py plans                                  what each plan films
    python fs25_video.py run <save> [--plan showcase] [--target "Tiger"] [--make] [...]
                                                                starts the game, films, cuts the clips
    python fs25_video.py record                                 records the running game until Enter (you play)
    python fs25_video.py cut <recording folder>                 finds and cuts the clips of a recording
    python fs25_video.py storyboard <clip folder> [--repo X]    writes storyboard.json (to edit)
    python fs25_video.py make <clip folder> [--repo X] [--style showcase] [--music generated|none|file]
                                            [--storyboard file] [--shorts] [--draft]
    python fs25_video.py sheet <clip folder>                    a contact sheet of the clips
    python fs25_video.py check <video>                          size, frame rate, loudness, black/frozen bits
    python fs25_video.py music <out.wav> <seconds> [--seed 2]   only the music
    python fs25_video.py list                                   recordings and videos made

Where things go: recordings, clips and videos in "<your user folder>/FS25 Video Studio" (VS_VIDEOS
changes it), not in Documents or Videos, which OneDrive often syncs: a master is a few GB.

What run does: checks (the game isn't running, the mod in your mods folder is this repo's version, the
save has it on), sets the game window to --window (1600x900) for this run, backs the save up, writes
the autorun file, starts the game through Steam, presses START, records the window and the game's sound
once the steps begin, ends the game without saving, puts the save and your window settings back, cuts
the clips and makes a contact sheet; with --make the finished video too.
"""
import argparse, datetime, glob, json, os, re, sys, threading, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vs_game as game  # noqa: E402
import vs_cut  # noqa: E402
import vs_edit  # noqa: E402
from vs_common import DOCS, VIDEOS, MOD_NAME, WIDTH, HEIGHT  # noqa: E402

PLANS = {
    "smoke": ["vsEnter", "vsShot static dur=3", "vsShot orbit dur=6", "quit"],
    "showcase": ["vsEnter", "vsLight golden", "vsShowcase", "vsShot colors", "vsLight off", "quit"],
    "quick": ["vsEnter", "vsLight golden", "vsShowcase quick", "vsLight off", "quit"],
    "colors": ["vsEnter", "vsLight midday", "vsShot colors", "vsLight off", "quit"],
    "building": ["vsEnter", "vsLight golden", "vsSun on", "vsShowcase building", "vsShot timelapse", "vsLight off", "quit"],
    "work": ["vsEnter", "vsLight midday", "vsWork on", "vsDrive 9", "wait 4", "vsShowcase work", "vsDrive stop", "vsWork off",
             "vsLight off", "quit"],
    "lights": ["vsEnter", "vsLight dawn", "vsShot arc", "vsLight morning", "vsShot pushin", "vsLight midday", "vsShot orbit dur=10",
               "vsLight golden", "vsShot crane", "vsLight night", "vsShot arc dur=8", "vsLight off", "quit"],
    "full": ["vsEnter", "vsLight golden", "vsShowcase", "vsShot colors", "vsLight morning", "vsShot drone", "vsShot arc side=right",
             "vsLight night", "vsShot orbit dur=12", "vsLight off", "quit"],
}
PLAN_TEXT = {
    "smoke": "a quick test: a still view and a short orbit (checks the whole chain)",
    "showcase": "golden hour: push in, orbit, reveal, hero arc, crane, fly-by, rear, drone, then every color",
    "quick": "golden hour: push in, orbit, hero arc, drone (about 45 s)",
    "colors": "every color at midday, the camera turning between them",
    "building": "a building: drone, orbit, push in, crane, fly-by, top-down, a day as a time-lapse",
    "work": "unfolds, lowers, switches on and drives straight on at 9 km/h: chase, alongside, lead, drive-past",
    "lights": "the same machine at dawn, in morning mist, midday, golden hour and at night",
    "full": "showcase + colors + morning mist + a night orbit with the lights on",
}


def with_target(steps, target):
    if not target:
        return steps
    return [f"vsTarget {target.strip()}"] + [s for s in steps if not s.startswith("vsTarget")]


def with_light(steps, light):
    if not light:
        return steps
    return [f"vsLight {light}" if s.startswith("vsLight") and s != "vsLight off" else s for s in steps]


# plans that film a parked vehicle: it goes to open ground first (a shed, trees, other machines are in
# the way where it's parked) and back at the end
MOVE_PLANS = {"smoke", "showcase", "quick", "colors", "lights", "full"}


def with_move(steps, move):
    if not move:
        return steps
    out = [s for s in steps if not s.startswith("vsMove")]
    # after the light is set (the machine turns to that light's sun), right before the first clip
    at = next((i for i, s in enumerate(out) if s.split()[0] in ("vsShot", "vsShowcase")), len(out))
    out.insert(at, "vsMove" if move is True else f"vsMove {move}")     # "move": "tree" = vsMove tree
    end = out.index("quit") if "quit" in out else len(out)
    out.insert(end, "vsMove back")
    return out


def with_options(steps, fov=None, folder=None):
    out = list(steps)
    at = next((i + 1 for i, s in enumerate(out) if s.startswith("vsEnter")), 0)
    if folder:
        out.insert(at, f"vsFolder {folder}")
    if fov:
        out.insert(at, f"vsFov {fov}")
    return out


def stamp():
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")



# ---------------------------------------------------------------- a video per mod: videos/<ModName>.json
MOD_PLANS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "videos")


def load_mod_plan(name):
    """videos/<ModName>.json (part of the name is enough):
    {"mod": "FS25_X", "save": 5, "target": "Tiger", "plan": "showcase" | "steps": [...], "move": true,
     "light": "golden", "style": "showcase", "music_seed": 2, "title": "...", "kicker": "...",
     "thumbnail": {"text": "...", "accent": "..."},
     "sections": {"orbit": {"caption": {...}, "keys": [...], "chapter": "..."}, "ui#2": {...}},
     "drop": ["rear"], "order": ["pushin", "ui", ...]}"""
    files = sorted(glob.glob(os.path.join(MOD_PLANS, "*.json")))
    hit = [f for f in files if os.path.basename(f)[:-5].lower() == name.lower()] or \
          [f for f in files if name.lower() in os.path.basename(f).lower()]
    if not hit:
        sys.exit(f"No plan for {name} in {MOD_PLANS} (fs25_video.py mods lists them)")
    with open(hit[0], encoding="utf-8") as f:
        plan = json.load(f)
    plan.setdefault("mod", os.path.basename(hit[0])[:-5])
    return plan


def apply_mod_plan(sb, plan):
    """The plan's words and choices on top of an automatic storyboard."""
    for k in ("title", "kicker", "line", "style", "grade", "bars", "music", "music_seed", "game_audio", "hook", "url", "description"):
        if k in plan:
            sb[k] = plan[k]
    if plan.get("thumbnail"):
        sb["thumbnail"].update(plan["thumbnail"])
    secs = sb["sections"]
    if plan.get("cuts") and secs:
        # one long clip filmed by hand, cut into steps: {"from": 4, "to": 12, "caption": {...}, "keys": [...]}
        clip = secs[0]["clip"]
        dur = _clip_seconds(sb, clip)
        secs = []
        for cut in plan["cuts"]:
            s = {k: v for k, v in cut.items() if k not in ("from", "to")}
            s.update(clip=clip, speed=1.0, trim=[float(cut["from"]), max(0.0, dur - float(cut["to"]))])
            secs.append(s)
        sb["sections"] = secs
        th = sb.setdefault("thumbnail", {})
        if plan.get("thumbnail", {}).get("second") is not None:
            th["clip"], th["at"] = clip, float(plan["thumbnail"]["second"]) / dur
        th.pop("second", None)
        sb["hook"] = None
        for s in secs:
            s.pop("title", None)
        secs[0]["title"] = True
        secs[-1]["end_card"] = True
        return sb
    if plan.get("drop"):
        secs = [s for s in secs if shot_of(s) not in plan["drop"]]
    # a plan with its own steps: only the shots those steps film (a remake from older clips leaves the rest out)
    steps = plan.get("steps") or []
    if steps and not any(st.split()[0] == "vsShowcase" for st in steps if st.split()):
        filmed = {st.split()[1] for st in steps if st.startswith("vsShot ") and len(st.split()) > 1}
        secs = [s for s in secs if shot_of(s) in filmed] or secs
    if plan.get("order"):
        rank = {name: i for i, name in enumerate(plan["order"])}
        secs.sort(key=lambda s: rank.get(shot_of(s), len(rank)))
    elif plan.get("kind") == "script":
        # a how-to tells its story in the order it was filmed (01_pov, 02_static, 03_pov ...)
        def filmed(s):
            head = os.path.basename(s["clip"]).split("_")[0]
            return int(head) if head.isdigit() else 0
        secs.sort(key=filmed)
        for s in secs[:-1]:
            s.pop("end_card", None)      # the end card goes on the last clip filmed
    seen = {}
    for s in secs:
        shot = shot_of(s)
        seen[shot] = seen.get(shot, 0) + 1
        for key in (f"{shot}#{seen[shot]}", shot):
            extra = (plan.get("sections") or {}).get(key)
            if extra:
                s.update(extra)
                break
    # the title sits on the first section, the end card on the last
    for s in secs:
        s.pop("title", None)
    if secs:
        secs[0]["title"] = True
        if not any(s.get("end_card") for s in secs):
            secs[-1]["end_card"] = True
    sb["sections"] = secs
    pick_thumbnail(sb, plan)
    return sb


def _clip_seconds(sb, clip):
    """A clip's length from the clips folder's clips.json (else probed)."""
    d = sb.get("clip_dir", "")
    try:
        with open(os.path.join(d, "clips.json"), encoding="utf-8") as f:
            for c in json.load(f)["clips"]:
                if c["file"] == clip:
                    return float(c["seconds"])
    except (OSError, ValueError, KeyError):
        pass
    from vs_common import probe
    return float(probe(os.path.join(d, clip)).get("duration") or 0)


def pick_thumbnail(sb, plan):
    """The thumbnail's clip: the plan's "shot" ("ui#2"), else for a how-to its first menu screen (not a
    machine that only opens the video), else the storyboard's pick if it is still in the video. The hook
    goes if its clip was left out."""
    secs = sb["sections"]
    if not secs:
        return
    th = sb.setdefault("thumbnail", {})
    in_video = {s["clip"] for s in secs}
    named, seen = {}, {}
    for s in secs:
        shot = shot_of(s)
        seen[shot] = seen.get(shot, 0) + 1
        named.setdefault(f"{shot}#{seen[shot]}", s)
        named.setdefault(shot, s)
    want = th.pop("shot", None)
    at = (plan.get("thumbnail") or {}).get("at", 0.6)
    ui = [s for s in secs if shot_of(s) == "ui"]
    if want and want in named:
        th["clip"], th["at"] = named[want]["clip"], at
    elif plan.get("kind") == "script" and ui:
        th["clip"], th["at"] = ui[0]["clip"], at
    elif th.get("clip") not in in_video:
        th["clip"], th["at"] = secs[0]["clip"], at
    if sb.get("hook") and sb["hook"].get("clip") not in in_video:
        sb["hook"] = None


def shot_of(section):
    """'03_orbit.mov' -> 'orbit'; '05_colors_Red.mov' -> 'colors'."""
    base = os.path.basename(section["clip"]).split(".")[0]
    parts = base.split("_")
    return parts[1] if len(parts) > 1 else base


def mod_steps(plan):
    steps = list(plan["steps"]) if plan.get("steps") else list(PLANS[plan.get("plan", "showcase")])
    steps = with_light(with_target(steps, plan.get("target")), plan.get("light"))
    steps = with_options(steps, plan.get("fov"), plan.get("folder") or plan["mod"])
    move = plan.get("move", not plan.get("steps") and plan.get("plan", "showcase") in MOVE_PLANS)
    return with_move(steps, move)


def batch_steps(plans):
    """Every plan's steps one after the other, for one game session; a menu left open is closed between."""
    steps = []
    for plan in plans:
        if steps:
            steps.append("vsMenu close")
        steps += mod_steps(plan)
    return steps


def plan_folder(plan):
    """The folder the mod writes a plan's clip lists to (vsFolder, as the mod's safeName makes it)."""
    return re.sub(r"[^A-Za-z0-9\-_]", "_", plan.get("folder") or plan["mod"])


def split_clips(clip_dir, plans, st):
    """A batch's clips, each mod's into <stamp>_<Mod>/clips/ with its own clips.json, by the folder of the
    clip list each clip came from. {mod: its clips folder}."""
    with open(os.path.join(clip_dir, "clips.json"), encoding="utf-8") as f:
        data = json.load(f)
    out = {}
    for plan in plans:
        folder = plan_folder(plan)
        mine = [c for c in data["clips"]
                if os.path.basename(os.path.dirname((c.get("run") or {}).get("list", ""))) == folder]
        if not mine:
            continue
        d = os.path.join(VIDEOS, f"{st}_{plan['mod']}", "clips")
        os.makedirs(d, exist_ok=True)
        for c in mine:
            src = os.path.join(clip_dir, c["file"])
            if os.path.isfile(src):
                os.replace(src, os.path.join(d, c["file"]))
        with open(os.path.join(d, "clips.json"), "w", encoding="utf-8") as f:
            json.dump(dict(data, clips=mine), f, indent=2)
        out[plan["mod"]] = d
    return out


def batch(names, make=True, shorts=False, draft=False, dry_run=False):
    """One game launch for several mods: every mod they need switched on at once, their steps one after the
    other, one recording; the clips go to each mod's folder and each mod's video is made."""
    if names == ["todo"]:
        names = [os.path.basename(f)[:-5] for f in sorted(glob.glob(os.path.join(MOD_PLANS, "*.json")))]
        names = [n for n in names if not video_done(load_mod_plan(n)["mod"])]
    plans = [load_mod_plan(n) for n in names]
    saves = sorted({p.get("save", 5) for p in plans})
    if len(saves) > 1:
        sys.exit(f"These plans use different savegames ({saves}): one batch per savegame")
    extra = sorted({m for p in plans for m in (p.get("with_mods") or [])})
    print(f"One session for {len(plans)} mod(s): {', '.join(p['mod'] for p in plans)}")

    def sort_and_make(clip_dir, st):
        parts = split_clips(clip_dir, plans, st)
        missing = [p["mod"] for p in plans if p["mod"] not in parts]
        for p in plans:
            if p["mod"] in parts:
                print(f"  {p['mod']}: {parts[p['mod']]}")
        if missing:
            print("! No clips for: " + ", ".join(missing))
        bad = 0
        for p in plans if make else []:
            if p["mod"] not in parts:
                continue
            print()
            print(f"=== {p['mod']}")
            try:
                make_video(parts[p["mod"]], repo=p["mod"], plan=p, shorts=shorts, draft=draft)
            except Exception as e:      # one video failing doesn't stop the others
                print(f"! {p['mod']}: {e}")
                bad += 1
        return 1 if missing or bad else 0

    return run(saves[0], batch_steps(plans), plan="batch", extra_mods=extra or None, dry_run=dry_run,
               timeout=max(3600, 900 * len(plans)), on_clips=sort_and_make)


COMPLETE = os.path.join(VIDEOS, "complete")


def complete(mods, echo=print):
    """Moves each mod's newest finished video into complete/ as <Mod>.mp4, with <Mod>_thumbnail.jpg and
    <Mod>_description.txt (an older one there is replaced). The clips stay in the run folder (--remake)."""
    import shutil
    os.makedirs(COMPLETE, exist_ok=True)
    moved = []
    for mod in mods:
        runs = sorted(glob.glob(os.path.join(VIDEOS, f"*_{mod}")))
        vids = [v for d in runs for v in glob.glob(os.path.join(d, "video", "*_1600x900.mp4"))]
        if not vids:
            echo(f"! {mod}: no finished video to move")
            continue
        vid = max(vids, key=os.path.getmtime)
        vdir = os.path.dirname(vid)
        shutil.move(vid, os.path.join(COMPLETE, f"{mod}.mp4"))
        for src, name in (("thumbnail.jpg", f"{mod}_thumbnail.jpg"), ("description.txt", f"{mod}_description.txt")):
            if os.path.isfile(os.path.join(vdir, src)):
                shutil.move(os.path.join(vdir, src), os.path.join(COMPLETE, name))
        moved.append(mod)
        echo(f"{mod}: {os.path.join(COMPLETE, mod + '.mp4')}")
    return moved


def video_done(mod):
    """The newest finished video of a mod (complete/ first), or None."""
    if os.path.isfile(os.path.join(COMPLETE, f"{mod}.mp4")):
        return os.path.join(COMPLETE, f"{mod}.mp4")
    vids = []
    for d in glob.glob(os.path.join(VIDEOS, f"*_{mod}")):
        vids += glob.glob(os.path.join(d, "video", "*_1600x900.mp4"))
    return max(vids, key=os.path.getmtime) if vids else None


# ---------------------------------------------------------------- run
def run(save, steps, plan="custom", window=(WIDTH, HEIGHT), audio=True, keep_open=False, anyway=False, dry_run=False,
        press=True, make=False, make_args=None, start_timeout=900, timeout=3600, keep_changed=False, extra_mods=None,
        on_clips=None):
    from vs_record import Recorder
    saves = {s["index"]: s for s in game.savegames()}
    if save not in saves:
        sys.exit(f"No savegame{save} in {DOCS} (see: saves)")
    sg = saves[save]
    problems = []
    if game.game_running():
        problems.append("the game is running: close it first")
    have, want = game.installed_version(), game.repo_version()
    if have is None:
        problems.append(f"{MOD_NAME}.zip isn't in your mods folder: install it first (this script never copies it there)")
    elif have != want:
        problems.append(f"your mods folder has {MOD_NAME} {have}, the repo is {want}: install the new zip first")
    if not sg["hasMod"]:
        problems.append(f"savegame{save} ({sg['name']}) doesn't have {MOD_NAME} switched on: add it in that save's mod list")
    for p in problems:
        print("! " + p)
    if problems and not anyway:
        sys.exit("Stopped (--anyway to try regardless).")
    if not keep_open and steps[-1:] != ["quit"]:
        steps = steps + ["quit"]
    renames = [r for r in game.farm_renames(sg["path"]) if r not in steps]
    steps = renames + steps        # first of all: no real farm names in any picture
    print(f"savegame{save}: {sg['name']} ({sg['map']}), window {window[0]}x{window[1]}, {len(steps)} steps:")
    for i, s in enumerate(steps, 1):
        print(f"  {i:2d}. {s}")
    if dry_run:
        print("Dry run: nothing written, game not started.")
        return 0

    st = stamp()
    rec_dir = os.path.join(VIDEOS, f"{st}_{plan}")
    os.makedirs(rec_dir, exist_ok=True)
    game_xml = os.path.join(DOCS, "game.xml")
    display_before = game.read_display(game_xml)
    game.write_display(game_xml, {"width": window[0], "height": window[1], "fullscreenMode": "windowed"})
    print(f"Window for this run: {window[0]}x{window[1]}, windowed (yours goes back afterwards: "
          f"{display_before['width']}x{display_before['height']} {display_before['fullscreenMode']})")
    zip_path, before = game.backup(sg["path"], stamp=st)
    print(f"Savegame backup: {zip_path}")
    added = game.with_mods(os.path.join(sg["path"], "careerSavegame.xml"), extra_mods)
    if added:
        print(f"Switched on for this run only: {', '.join(added)}")
    started_at = time.time()
    game.write_autorun(steps, save)
    log_path = os.path.join(DOCS, "log.txt")
    watch = game.LogWatch()
    recorder = Recorder(rec_dir, audio=audio)
    result = 1
    stop = threading.Event()
    t = None
    try:
        game.start_game(save)
        print("Starting the game through Steam ...")
        launched = time.time()
        if not game.wait_for(lambda: game.game_running() or game.steam_waiting(launched), 180) or not game.game_running():
            waiting = game.steam_waiting(launched)
            if waiting:
                print(f"! Steam is waiting for an answer before it starts the game: {waiting}")
                print("  Answer the dialog in Steam (it's not answered for you), then run again.")
                return 2
            print("! The game didn't start within 3 minutes")
            return 1
        t = threading.Thread(target=game.follow_log, args=(log_path, started_at - 5, watch, stop.is_set), daemon=True)
        t.start()
        presser = game.StartPresser(enabled=press)
        if not game.wait_for(lambda: presser.tick(watch) or watch.started or watch.refused or not game.game_running(), start_timeout):
            print(f"! No autorun after {start_timeout // 60} min. Waiting at a start screen? Is the mod on in that save?")
        elif watch.refused:
            print("! The mod didn't run the steps (see above)")
        elif not game.game_running():
            print(f"! The game ended before the steps (crash: {game.crash_logged(started_at) or 'none logged'})")
        else:
            _, size = game.game_window()
            print(f"Game window: {size[0]}x{size[1]}" if size else "! Game window not found")
            recorder.start()
            typer = game.KeyTyper()
            finished = game.wait_for(lambda: typer.tick(watch) or watch.done or not game.game_running(), timeout, poll=0.3)
            if watch.done:
                result = 0
                time.sleep(1.0)
            elif finished:
                print(f"! The game ended during step {watch.step} (crash: {game.crash_logged(started_at) or 'none logged'})")
            else:
                print(f"! Steps not done after {timeout // 60} min")
        meta = recorder.stop()
        if meta:
            print(f"Recorded {meta.get('seconds', 0):.0f} s at {meta.get('width')}x{meta.get('height')}"
                  + (", with game sound" if meta.get("audio") else ", no game sound"))
        if not keep_open and game.game_running() and not game.wait_for(lambda: not game.game_running(), 20):
            print("Ending the game (without saving)")
    except KeyboardInterrupt:
        print("Stopped")
        recorder.stop()
    finally:
        stop.set()
        if t is not None:
            t.join(timeout=3)
        game.remove_autorun()
        if not keep_open:
            if game.game_running():
                game.end_game()
                game.wait_for(lambda: not game.game_running(), 30)
            time.sleep(2)
            kept = game.restore_if_changed(sg["path"], zip_path, before, stamp=st)
            if kept and not keep_changed:
                import shutil
                shutil.rmtree(kept, ignore_errors=True)       # the game's autosave as it quit: not wanted
                print(f"The game wrote to savegame{save} (autosave): put back as it was")
            elif kept:
                print(f"The game wrote to savegame{save}: backup put back, the changed one is in {kept}")
            else:
                print(f"savegame{save} unchanged")
            game.prune_backups()
            game.write_display(game_xml, display_before)
            print("Your window settings are back in game.xml")
        if os.path.isfile(log_path):
            import shutil
            shutil.copy2(log_path, os.path.join(rec_dir, "log.txt"))
    print(f"\nlog: {watch.errors} error line(s) (other mods too); {watch.clip_done} clip(s) filmed")
    if not os.path.isfile(os.path.join(rec_dir, "master.mkv")):
        return result or 1
    clips = vs_cut.cut(rec_dir, since=started_at - 5)
    if not clips:
        print("! No clips found in the recording")
        return 1
    clip_dir = os.path.join(rec_dir, "clips")
    sheet = vs_cut.contact_sheet(clip_dir)
    print(f"\nClips: {clip_dir}\nContact sheet: {sheet}")
    if on_clips is not None:
        return on_clips(clip_dir, st) or result
    if make:
        return make_video(clip_dir, **(make_args or {}))
    return result


def record(audio=True, seconds=None):
    """Records the running game (you play, with the keys or console) until Enter, then cuts the clips."""
    from vs_record import Recorder
    if not game.game_running():
        sys.exit("The game isn't running")
    rec_dir = os.path.join(VIDEOS, f"{stamp()}_manual")
    r = Recorder(rec_dir, audio=audio)
    started = time.time()
    r.start()
    try:
        if seconds:
            time.sleep(seconds)
        else:
            input("Recording: film with Right Shift + 1..4 or vsShot in the game. Enter here to stop. ")
    except KeyboardInterrupt:
        pass
    meta = r.stop()
    print(f"Recorded {meta.get('seconds', 0):.0f} s")
    clips = vs_cut.cut(rec_dir, since=started - 5)
    if clips:
        print("Contact sheet:", vs_cut.contact_sheet(os.path.join(rec_dir, "clips")))
    return 0


def make_video(clip_dir, repo=None, style="showcase", title=None, music="generated", storyboard=None, shorts=False,
               draft=False, brand="auto", out=None, seed=None, game_audio=None, clean=False, plan=None):
    if storyboard:
        with open(storyboard, encoding="utf-8") as f:
            sb = json.load(f)
        sb.setdefault("clip_dir", os.path.abspath(clip_dir))
    else:
        sb = vs_edit.auto_storyboard(clip_dir, repo=repo, style=(plan or {}).get("style", style), title=title,
                                     music=music, brand=brand)
    if plan is not None:
        sb = apply_mod_plan(sb, plan)
    if seed is not None:
        sb["music_seed"] = seed
    if game_audio is not None:
        sb["game_audio"] = game_audio
    out = out or os.path.join(os.path.dirname(os.path.abspath(clip_dir)), "video")
    res = vs_edit.render(sb, out, draft=draft, shorts=shorts, clean=clean)
    print(f"\nVideo: {res['video']} ({res['seconds']:.0f} s)")
    for k in ("thumbnail", "teaser", "shorts"):
        if res.get(k):
            print(f"{k.capitalize()}: {res[k]}")
    print(f"Description: {os.path.join(out, 'description.txt')}" + ("" if res.get("chapters") else " (no chapters: too short)"))
    for level, text in vs_edit.check(res["video"]):
        print(f"  {level:2s} {text}")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("saves")
    sub.add_parser("plans")
    sub.add_parser("list")
    r = sub.add_parser("run")
    r.add_argument("save", type=int)
    r.add_argument("--plan", choices=sorted(PLANS), default="showcase")
    r.add_argument("--steps", nargs="+", help='your own steps instead of a plan: --steps "vsEnter" "vsShot orbit dur=20"')
    r.add_argument("--target", help="what to film, part of its name (vsTarget)")
    r.add_argument("--light", help="light instead of the plan's: golden, morning, midday, overcast, dawn, night")
    r.add_argument("--fov", type=float, help="field of view for every shot (default 40)")
    r.add_argument("--folder", help="folder name for the clip lists (vsFolder)")
    r.add_argument("--move", dest="move", action="store_true", default=None,
                   help="move the vehicle to open ground first (default for vehicle plans)")
    r.add_argument("--no-move", dest="move", action="store_false", help="film it where it stands")
    r.add_argument("--window", default=f"{WIDTH}x{HEIGHT}", help="the game window for this run (1600x900; bigger = sharper, scaled down)")
    r.add_argument("--no-audio", action="store_true", help="don't record the game's sound")
    r.add_argument("--keep-open", action="store_true")
    r.add_argument("--keep-changed", action="store_true", help="keep the savegame as the game left it (in autorun/)")
    r.add_argument("--anyway", action="store_true")
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--no-press", action="store_true")
    r.add_argument("--make", action="store_true", help="make the finished video afterwards")
    for sp in (r, sub.add_parser("make"), sub.add_parser("storyboard")):
        if sp is not r:
            sp.add_argument("clips")
        sp.add_argument("--repo", help="the filmed mod's repo (name or path): title, version, description")
        sp.add_argument("--style", choices=sorted(vs_edit.STYLES), default="showcase")
        sp.add_argument("--title")
        sp.add_argument("--music", default="generated", help="generated, none, or a music file")
        sp.add_argument("--brand", default="auto", help="auto, dtm, neutral or a brand .json")
        if sp.prog.endswith("make") or sp is r:
            sp.add_argument("--storyboard", help="render this storyboard.json instead of a new one")
            sp.add_argument("--shorts", action="store_true", help="also a 1080x1920 YouTube Shorts version")
            sp.add_argument("--draft", action="store_true", help="fast and rough (to check the cut)")
            sp.add_argument("--seed", type=int, help="another generated tune")
            sp.add_argument("--game-audio", type=float, help="game sound level under the music (0..1, default 0.45)")
            sp.add_argument("--out")
            sp.add_argument("--clean", action="store_true", help="delete the _work folder afterwards")
    mp = sub.add_parser("mod", help="film and make one mod's video from videos/<ModName>.json")
    mp.add_argument("name")
    mp.add_argument("--save", type=int, help="another savegame than the plan's")
    mp.add_argument("--no-make", action="store_true", help="film and cut only")
    mp.add_argument("--remake", help="make the video again from this clips folder (no game)")
    mp.add_argument("--shorts", action="store_true")
    mp.add_argument("--draft", action="store_true")
    mp.add_argument("--dry-run", action="store_true")
    sub.add_parser("mods", help="every mod plan and whether its video is made")
    cp = sub.add_parser("complete", help="move mods' finished videos into complete/ (named by mod)")
    cp.add_argument("names", nargs="+", help="mod plans (part of the name)")
    bp = sub.add_parser("batch", help="film several mods in ONE game session, then make each one's video")
    bp.add_argument("names", nargs="+", help="mod plans (part of the name); todo = every plan without a video yet")
    bp.add_argument("--no-make", action="store_true", help="film, cut and sort the clips only")
    bp.add_argument("--shorts", action="store_true")
    bp.add_argument("--draft", action="store_true")
    bp.add_argument("--dry-run", action="store_true")
    rc = sub.add_parser("record")
    rc.add_argument("--no-audio", action="store_true")
    rc.add_argument("--seconds", type=float)
    c = sub.add_parser("cut")
    c.add_argument("recording")
    c.add_argument("--trim", type=int, default=2, help="frames left out next to each card")
    s = sub.add_parser("sheet")
    s.add_argument("clips")
    k = sub.add_parser("check")
    k.add_argument("video")
    m = sub.add_parser("music")
    m.add_argument("out")
    m.add_argument("seconds", type=float)
    m.add_argument("--seed", type=int, default=1)
    m.add_argument("--key", default="D")
    m.add_argument("--bpm", type=float, default=92)
    a = p.parse_args(argv)

    if a.cmd == "saves":
        rows = game.savegames()
        for sv in rows:
            print(f"{sv['index']:3d}  {'mod on ' if sv['hasMod'] else '       '}  {sv['name'][:30]:30s}  {sv['map'][:24]:24s}  {sv['date']}")
        print(f"\ninstalled {MOD_NAME}: {game.installed_version() or 'none'}, repo: {game.repo_version()}")
        return 0
    if a.cmd == "plans":
        for name in sorted(PLANS):
            print(f"{name:9s} {PLAN_TEXT[name]}\n          " + " / ".join(PLANS[name]))
        return 0
    if a.cmd == "list":
        for d in sorted(glob.glob(os.path.join(VIDEOS, "*"))):
            clips = os.path.join(d, "clips", "clips.json")
            n = len(json.load(open(clips, encoding="utf-8"))["clips"]) if os.path.isfile(clips) else 0
            vids = glob.glob(os.path.join(d, "video", "*.mp4"))
            print(f"{os.path.basename(d):40s} {n:3d} clip(s)  " + ", ".join(os.path.basename(v) for v in vids))
        print(f"\n{VIDEOS}")
        return 0
    if a.cmd == "run":
        steps = list(a.steps) if a.steps else list(PLANS[a.plan])
        move = a.move if a.move is not None else (not a.steps and a.plan in MOVE_PLANS)
        steps = with_move(with_options(with_light(with_target(steps, a.target), a.light), a.fov, a.folder), move)
        w, _, h = a.window.partition("x")
        make_args = {"repo": a.repo, "style": a.style, "title": a.title, "music": a.music, "brand": a.brand,
                     "shorts": a.shorts, "draft": a.draft, "seed": a.seed, "game_audio": a.game_audio, "clean": a.clean}
        return run(a.save, steps, plan=a.plan if not a.steps else "custom", window=(int(w), int(h)), audio=not a.no_audio,
                   keep_open=a.keep_open, keep_changed=a.keep_changed, anyway=a.anyway, dry_run=a.dry_run, press=not a.no_press, make=a.make,
                   make_args=make_args)
    if a.cmd == "mods":
        for f in sorted(glob.glob(os.path.join(MOD_PLANS, "*.json"))):
            plan = json.load(open(f, encoding="utf-8"))
            mod = plan.get("mod", os.path.basename(f)[:-5])
            done = video_done(mod)
            print(f"{mod:38s} {plan.get('kind', '?'):9s} save {plan.get('save', '?'):>2}  "
                  + (f"made: {os.path.basename(os.path.dirname(os.path.dirname(done)))}" if done else "not made yet"))
        return 0
    if a.cmd == "mod":
        plan = load_mod_plan(a.name)
        if a.remake:
            return make_video(a.remake, repo=plan["mod"], plan=plan, shorts=a.shorts, draft=a.draft)
        steps = mod_steps(plan)
        return run(a.save or plan.get("save", 5), steps, plan=plan["mod"], window=tuple(plan.get("window", (WIDTH, HEIGHT))),
                   audio=plan.get("audio", True), dry_run=a.dry_run, make=not a.no_make, extra_mods=plan.get("with_mods"),
                   make_args={"repo": plan["mod"], "plan": plan, "shorts": a.shorts, "draft": a.draft})
    if a.cmd == "complete":
        return 0 if complete([load_mod_plan(n)["mod"] for n in a.names]) else 1
    if a.cmd == "batch":
        return batch(a.names, make=not a.no_make, shorts=a.shorts, draft=a.draft, dry_run=a.dry_run)
    if a.cmd == "record":
        return record(audio=not a.no_audio, seconds=a.seconds)
    if a.cmd == "cut":
        clips = vs_cut.cut(a.recording, trim=a.trim, since=0)
        if clips:
            print("Contact sheet:", vs_cut.contact_sheet(os.path.join(a.recording, "clips")))
        return 0 if clips else 1
    if a.cmd == "sheet":
        print(vs_cut.contact_sheet(a.clips))
        return 0
    if a.cmd == "storyboard":
        sb = vs_edit.auto_storyboard(a.clips, repo=a.repo, style=a.style, title=a.title, music=a.music, brand=a.brand)
        path = os.path.join(a.clips, "storyboard.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(sb, f, indent=2)
        print(path)
        return 0
    if a.cmd == "make":
        return make_video(a.clips, repo=a.repo, style=a.style, title=a.title, music=a.music, storyboard=a.storyboard,
                          shorts=a.shorts, draft=a.draft, brand=a.brand, out=a.out, seed=a.seed, game_audio=a.game_audio,
                          clean=a.clean)
    if a.cmd == "check":
        bad = 0
        for level, text in vs_edit.check(a.video):
            print(f"{level:2s} {text}")
            bad += level == "!"
        return 1 if bad else 0
    if a.cmd == "music":
        import vs_music
        print(vs_music.write(a.out, a.seconds, a.seed, a.key, a.bpm))
        return 0


if __name__ == "__main__":
    sys.exit(main())
