# TFLX_ReName — Development Handoff Document

## What this tool is

A Python/Tkinter desktop utility (`TFLX_ReName.pyw`) that watches one or more folders
for new `.tflx` files (Trimble FieldLink survey database files) and prompts the user to
rename and move them using a standardized naming convention:

```
Building-Level-Area-Tablet-MMDDYY_HHMM.tflx
```

After rename, the file is moved to a structured dump folder:
```
DumpFolder\Building\Level\Area\
```

Config (watch folders, dump folder) is saved to `tflx_watcher_config.json` next to the script.
The tool uses `watchdog` for filesystem monitoring and `tkinter` for the GUI.
It runs as a `.pyw` file (no console window in normal use); renamed to `.py` for debugging.

---

## The persistent bug — FULL HISTORY

**Every time a new `.tflx` file is dropped into a watched folder, 2–5 rename popups appear
instead of one.**

This has been the sole focus of the development effort across 12 versions. The root cause
is a Tkinter behavior on Windows where `Toplevel.__init__()` and `messagebox` functions
internally flush (pump) the Tk event queue, causing re-entrant execution of callbacks
that were waiting in the queue.

---

## Version history (v1–v12)

### v1 — Original
- Used `watchdog` `on_created` only
- `WatcherApp` polled a `queue.Queue` every 500ms via `root.after()`
- A `messagebox.askyesno("Would you like to rename?")` pre-prompt preceded `RenamePopup`
- **Result: 2 popups**

### v2 — `_pending` set in handler
- Added a `_pending` set to `TFLXHandler` to block duplicate `on_created` events while
  a timer was running
- Cleared `_pending` when the timer fired
- **Result: 3 popups** — `on_modified` events arriving after the timer window bypassed the guard

### v3 — `DedupeQueue` + `on_modified`
- Replaced `queue.Queue` with a custom `DedupeQueue` that tracked in-flight paths
- Added `on_modified` to the handler
- `mark_done()` called when popup closed to release the path from `DedupeQueue`
- **Result: still 2 popups**

### v4 — `_shown` set in `WatcherApp`
- Reverted handler to simple `on_created` only
- Added `self._shown` set in `WatcherApp` — paths added on first popup, never shown again
- **Result: still 3 popups**

### v5 — Removed blocking `messagebox.askyesno`
- Identified that `messagebox.askyesno` internally pumps the Tkinter event loop via
  `wait_window()`, allowing re-entrant `_poll_queue` calls while the dialog was on screen
- Removed the pre-prompt entirely — now goes straight to `RenamePopup` (which uses
  `grab_set()` for proper modal behavior)
- Also fixed: Cancel button previously only called `on_done()`/`destroy()` if the user
  confirmed deletion — clicking "No" on the delete confirm left `_popup_open = True`
  permanently, freezing the watcher
- **Result: still 2–3 popups**

### v6 — Added `on_modified` and `on_moved` to handler
- Suspected OneDrive was generating extra events (watch folder is a OneDrive path)
- Added `on_modified` and `on_moved` (OneDrive renames temp→final file)
- **Result: still multiple popups** — user confirmed bug also occurs on tablets not using OneDrive

### v7 — Debug logging build
- Added `[Version]`, `[Event]`, `[Queue]`, `[Poll]`, `[Popup]`, `[Blocked]`, `[Done]` print
  statements throughout
- **Debug output revealed:** 3 items were already sitting in the queue before the first
  `_poll_queue` call ran. A 4th arrived while the popup was open. `shown=set()` and
  `popup_open=False` on the first poll — guards were correct but being bypassed.
- **Root cause identified:** `Toplevel.__init__` on Windows flushes pending Tk events
  internally when creating a new window. This re-enters `_poll_queue` (via the `after(500)`
  callback chain) mid-execution, before the function returns. No flag set inside `_poll_queue`
  can protect against this because the re-entry happens before the flag write completes.

### v8 — Eliminated polling loop entirely
- Replaced the `queue.Queue` + `root.after(500, _poll_queue)` architecture with direct
  `root.after(0, _try_show, path)` posting from the watchdog timer thread
- `root.after(0, ...)` is Tkinter's thread-safe event posting mechanism — callbacks are
  queued and executed serially on the main thread, one at a time
- `_try_show()` checks `_shown` and `_popup_open` before acting
- No pre-prompt — goes straight to RenamePopup
- **Result: one popup only, but user noticed the pre-prompt ("new file detected") was missing**

### v9 — Bug fixes from code review (Opus)
An Opus-level code review identified several issues. Three were applied:
1. **`WM_DELETE_WINDOW` handler on `RenamePopup`** — clicking the window X button previously
   left `_popup_open = True` permanently, freezing the watcher. Now calls `on_done(renamed=False)`
   and destroys the window.
2. **Timer debounce in `TFLXHandler`** — NTFS fires 10–20 events per file copy. Previously each
   spawned a separate `threading.Timer`, all of which eventually posted `after(0, _try_show)`.
   Now a `_timers` dict keyed by lowercase filename cancels the previous timer before starting
   a new one, so at most one `_try_show` call per file. Thread-safe via `threading.Lock`.
3. **Dead `import queue` removed** — leftover from the old polling architecture (two locations).
4. **`path.exists()` guard in `_try_show`** — if the file was already moved/renamed by the time
   the debounced timer fires, the popup is skipped silently.
- **Result: tested on tablet — one popup, dedup working. But user wanted the pre-prompt back.**

### v10 — Re-added pre-prompt via `messagebox.askyesno`
- Brought back `messagebox.askyesno("New file detected — rename now?")` before `RenamePopup`
- Theory: safe because `_popup_open` is set before the messagebox opens, so re-entrant
  `_try_show` calls during the event pump should hit the guard
- **Result: 3 pre-prompts appeared** — `messagebox.askyesno` uses `wait_window()` internally,
  which pumps the Tk event loop. The pump processes pending `after(0, _try_show)` calls,
  but those calls see `_popup_open=True` and `_shown` already populated — so they Skip.
  However, the `wait_window()` pump appears to also be creating additional messagebox
  instances through some internal Tk mechanism. The guards work for `_try_show` re-entrancy
  but cannot prevent the messagebox machinery itself from duplicating.

### v11 — Custom `DetectedPrompt` Toplevel (replaces messagebox)
- Created `DetectedPrompt(tk.Toplevel)` — a non-blocking modal prompt with callback-driven
  Yes/No buttons, `grab_set()` for modality, `WM_DELETE_WINDOW` handler
- No `wait_window()`, no event loop pump from the prompt itself
- **Result: 2 popups** — `Toplevel.__init__()` in `DetectedPrompt` itself flushes Tk events
  during window creation, and that flush processes queued `after(0, _try_show)` calls
  before the constructor returns. Even though `_popup_open` is already True, the flush
  creates a second `DetectedPrompt` window through re-entrant construction.

### v12 — Deferred window creation via `after(1, ...)` (CURRENT)
- Both `DetectedPrompt` and `RenamePopup` are now created via `self.root.after(1, lambda: ...)`
  instead of directly
- The sequence is:
  1. `_try_show` runs synchronously — sets `_shown` and `_popup_open`, then returns
  2. Back in the Tk event loop, any remaining `after(0, _try_show)` calls execute and get
     blocked by `_popup_open`
  3. Only after the queue is drained does the `after(1)` callback fire and create the Toplevel
  4. When `Toplevel.__init__` flushes events internally, there's nothing left to cause trouble
- **Result: NOT YET CLEANLY TESTED** — user's test was contaminated by old Python processes
  from previous versions still running and watching the same folder. The screenshot showed
  standard Windows `messagebox.askyesno` dialogs (with "Yes / No" buttons) that don't exist
  anywhere in v12. User needs to kill all `python.exe` / `pythonw.exe` processes via Task
  Manager's Details tab and retest with only v12 running.

---

## Key facts about the environment

- Windows 11 tablets (Trimble field tablets) and a Windows laptop
- Watch folder: sometimes a OneDrive-synced folder, sometimes local — bug occurs in both
- `.pyw` extension — runs without a console window normally; renamed to `.py` for debugging
- `watchdog` library for filesystem events
- Python 3.12+
- The tool is run by non-developers; it needs to be a single `.pyw` file, no installer
- NTFS fires many filesystem events (created, modified, etc.) for a single file copy operation
- OneDrive may add additional events (temp file → rename to final) but is not the root cause

---

## Current architecture (v12)

### Event flow
```
NTFS events → watchdog thread → TFLXHandler._schedule()
    → debounce: cancel previous Timer for same filename, start new 2-sec Timer
    → Timer fires: root.after(0, _try_show, path)  [thread-safe Tk posting]
    → Tk main thread processes _try_show:
        → guards: path.exists()? already in _shown? _popup_open?
        → if clear: set _shown + _popup_open, return immediately
        → after(1): DetectedPrompt created (queue is now empty, safe from flush)
        → user clicks Yes: after(1): RenamePopup created
        → user clicks No / X: _on_popup_done() unlocks watcher
        → RenamePopup closes: _on_popup_done() pops next from _pending
```

### Classes
- `LauncherWindow` — startup config UI (watch folders, dump folder, Start button)
- `TFLXHandler(FileSystemEventHandler)` — watchdog handler with timer debounce;
  posts to Tk main thread via `root.after(0, ...)`
- `DetectedPrompt(tk.Toplevel)` — non-blocking "New file detected — rename now?" modal;
  callback-driven buttons, no `wait_window()`, has `WM_DELETE_WINDOW` handler
- `WatcherApp` — manages observers, `_shown` set, `_pending` list, `_try_show()`,
  `_on_popup_done()`, `_open_rename()`, `_decline_rename()`
- `RenamePopup(tk.Toplevel)` — the rename/move dialog; `grab_set()` modal;
  Cancel button offers to delete the file; has `WM_DELETE_WINDOW` handler

### File structure
```
tflx_watcher_config.json    — auto-generated config
TFLX_ReName_v12.pyw         — current version of the tool
```

---

## What the next session should focus on

1. **Clean test of v12** — user needs to kill ALL python/pythonw processes first. The last
   test was contaminated by old versions. The console log and the custom `DetectedPrompt`
   window style are the indicators that v12 is the one actually running. Standard Windows
   messageboxes with "Yes / No" mean an old version is still alive.

2. **If v12 still shows duplicates after a clean test**, the `after(1)` delay may not be
   sufficient. Possible next steps:
   - Increase delay to `after(50)` or `after(100)` to ensure queue is fully drained
   - Add a boolean `_prompt_active` flag checked inside DetectedPrompt.__init__ itself
     as a last-resort guard
   - As a nuclear option: skip Toplevel entirely and use a simple inline widget embedded
     in the main (withdrawn) Tk root, shown via `deiconify()` — no Toplevel creation at all

3. **Cancel button UX** — currently "Cancel" on the RenamePopup offers to delete the file.
   The code review recommended restructuring to: Rename & Move (primary), Skip (close, leave
   file), and optionally Delete (red, destructive, with confirmation). This hasn't been
   implemented yet.

4. **Observer references** — `Observer` objects are created as local variables in a loop inside
   `_start_observers()`. They survive because daemon threads hold references, but storing them
   on `self._observers` would be cleaner and enable a future "Stop Watching" feature.

5. **Hardcoded project values** — `BUILDINGS`, `AREAS`, `LEVELS`, `TABLETS` are hardcoded for
   the current DG/SSB job. For distribution, these should come from the config file.

---

## The user (Pete)

Pete is a construction foreman working on a large commercial mechanical tower project. He uses
Trimble FieldLink with multiple field tablets and robotic total stations. He's also the developer
of `tflx_merge_tool.py` — a much larger Python/Tkinter tool for managing FieldLink database
files. He's technically capable but not a professional developer. He tests on real field
hardware (Windows 11 tablets) and provides clear feedback with screenshots and console logs.
He works iteratively and appreciates direct, grounded explanations.
