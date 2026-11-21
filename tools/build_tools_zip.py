"""Builds VideoStudio_Tools.zip: everything besides the mod, for recording and editing.

    python tools/build_tools_zip.py [out_dir]          (default: dist)

The release has two zips: FS25_VideoStudio.zip goes into the game's mods folder, this one is unzipped
anywhere. Inside, all in VideoStudio_Tools/: the tools (runner, recorder, cutter, editor, music, the .cmd
shortcuts), the brand presets, the VS Code tasks, the tests, the README, and modDesc.xml plus the mod's
script (the runner checks the installed mod against this version; the tests run the script). The folder
and the name without "FS25_" keep the game from taking it for a second copy of the mod.

Only files tracked by git go in (no __pycache__, no local leftovers).
"""
import os, subprocess, sys, zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAME = "VideoStudio_Tools"
INCLUDE = ("tools/", "tests/", "presets/", ".vscode/tasks.json", "scripts/VideoStudio.lua", "modDesc.xml",
           "README.md", "LICENSE.txt")


def tracked():
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [f for f in out.splitlines() if f.startswith(INCLUDE) and "__pycache__" not in f]


def build(out_dir="dist"):
    out_dir = os.path.join(ROOT, out_dir) if not os.path.isabs(out_dir) else out_dir
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, NAME + ".zip")
    files = tracked()
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.write(os.path.join(ROOT, f), f"{NAME}/{f}")
    print(f"{path}: {len(files)} files, {os.path.getsize(path) // 1024} KB")
    return path, files


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else "dist")
