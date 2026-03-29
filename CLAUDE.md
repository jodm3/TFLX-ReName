# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Single-file Python desktop tool (`TFLX ReName.py`) that watches filesystem folders for new `.tflx` files and prompts the user to rename and organize them via a tkinter GUI. Files are renamed using the convention `Building-Level-Area-Tablet-MMDDYY_HHMM.tflx` and moved into a structured dump folder (`DumpFolder/Building/Level/Area/`).

## Running

```bash
pip install watchdog
python "TFLX ReName.py"
```

The only external dependency is `watchdog`. Everything else uses the Python standard library (tkinter, pathlib, shutil, json, threading).

## Architecture

The app is a single file with four main classes in a pipeline:

1. **`LauncherWindow`** — Config UI for selecting watch folders and dump folder. Saves/loads `tflx_watcher_config.json` next to the script.
2. **`TFLXHandler`** (watchdog `FileSystemEventHandler`) — Detects new `.tflx` files and enqueues them after a 2-second settle delay.
3. **`WatcherApp`** — Polls the file queue every 500ms and spawns rename popups. Only one popup can be open at a time (`_popup_open` flag).
4. **`RenamePopup`** — Modal dialog where the user picks Building/Level/Area/Tablet, previews the new filename, and confirms the move.

## Domain Rules

- **Buildings**: `DG` and `SSB`. When building is `SSB`, the Area field is disabled and omitted from the filename (format becomes `SSB-Level-Tablet-MMDDYY_HHMM.tflx`).
- **Levels**: `UG`, then `01`–`23`.
- **Areas**: `Tower`, `Podium` (only for `DG`).
- **Tablets**: `T1`–`T4`.
- Config persists to `tflx_watcher_config.json`. Legacy single `watch_folder` key is auto-migrated to `watch_folders` array.
