"""
TFLX File Watcher & Rename Tool
Watches one or more folders for new .tflx files and prompts for standardized renaming.
Naming convention: Building-Level-Area-Tablet-MMDDYY_HHMM.tflx
After rename, moves file to: DumpFolder/Building/Level/Area/
Config saved to tflx_watcher_config.json next to this script.
"""

import sys
import json
import queue
import shutil
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

DEFAULT_WATCH_FOLDERS = [r"C:\TFLXExports"]
DEFAULT_DUMP_FOLDER   = r"C:\TFLXDump"
FILE_EXTENSION        = ".tflx"
COPY_SETTLE_DELAY     = 2.0
CONFIG_FILE           = Path(__file__).parent / "tflx_watcher_config.json"

LEVELS    = ["UG"] + [f"{n:02d}" for n in range(1, 24)]
BUILDINGS = ["DG", "SSB"]
AREAS     = ["Tower", "Podium"]
TABLETS   = ["T1", "T2", "T3", "T4"]


# ── Config helpers ────────────────────────────────────────────────────────────

def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text())
            if "watch_folder" in data and "watch_folders" not in data:
                data["watch_folders"] = [data.pop("watch_folder")]
            return data
        except Exception:
            pass
    return {"watch_folders": DEFAULT_WATCH_FOLDERS, "dump_folder": DEFAULT_DUMP_FOLDER}


def save_config(cfg: dict):
    try:
        CONFIG_FILE.write_text(json.dumps(cfg, indent=2))
    except Exception as e:
        print(f"[Config] Could not save: {e}")


# ── Watchdog handler ──────────────────────────────────────────────────────────

class TFLXHandler(FileSystemEventHandler):
    def __init__(self, file_queue):
        super().__init__()
        self._file_queue = file_queue

    def on_created(self, event):
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix.lower() == FILE_EXTENSION:
            threading.Timer(COPY_SETTLE_DELAY, self._enqueue, args=[path]).start()

    def _enqueue(self, path):
        if path.exists():
            self._file_queue.put(path)


# ── Launcher / config window ──────────────────────────────────────────────────

class LauncherWindow:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("TFLX Watcher — Setup")
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)

        cfg = load_config()
        self._folders     = list(cfg.get("watch_folders", DEFAULT_WATCH_FOLDERS))
        self._dump_folder = tk.StringVar(value=cfg.get("dump_folder", DEFAULT_DUMP_FOLDER))

        self._build_ui()
        self._refresh_list()
        self._center()
        self.root.deiconify()

    def _build_ui(self):
        hdr = tk.Frame(self.root, bg="#1a3a5c")
        hdr.pack(fill="x")
        tk.Label(hdr, text="  TFLX File Watcher",
                 bg="#1a3a5c", fg="white",
                 font=("Segoe UI", 13, "bold"),
                 pady=12, padx=12).pack(anchor="w")
        tk.Label(hdr, text="  Configure folders to watch for new exports",
                 bg="#1a3a5c", fg="#aac4e0",
                 font=("Segoe UI", 9), pady=0, padx=12).pack(anchor="w")
        tk.Label(hdr, text="", bg="#1a3a5c").pack()

        body = tk.Frame(self.root, padx=16, pady=14)
        body.pack(fill="both", expand=True)

        # ── Watch Folders ──
        tk.Label(body, text="Watch Folders",
                 font=("Segoe UI", 9, "bold"), anchor="w").pack(anchor="w")
        tk.Label(body,
                 text="New .tflx files in any of these folders (and subfolders) will trigger the popup.",
                 font=("Segoe UI", 8), fg="#666", anchor="w").pack(anchor="w", pady=(0, 8))

        list_frame = tk.Frame(body)
        list_frame.pack(fill="x")
        scrollbar = tk.Scrollbar(list_frame, orient="vertical")
        self.listbox = tk.Listbox(
            list_frame, font=("Consolas", 9),
            height=4, width=55,
            selectmode="single",
            yscrollcommand=scrollbar.set,
            activestyle="none",
            relief="solid", bd=1
        )
        scrollbar.config(command=self.listbox.yview)
        self.listbox.pack(side="left", fill="x", expand=True)
        scrollbar.pack(side="left", fill="y")

        watch_btns = tk.Frame(body)
        watch_btns.pack(anchor="w", pady=(6, 0))
        tk.Button(watch_btns, text="+ Add Folder",
                  font=("Segoe UI", 9), relief="flat", bg="#e8edf2",
                  cursor="hand2", padx=8, pady=3,
                  command=self._add_folder).pack(side="left", padx=(0, 6))
        tk.Button(watch_btns, text="− Remove Selected",
                  font=("Segoe UI", 9), relief="flat", bg="#e8edf2",
                  cursor="hand2", padx=8, pady=3,
                  command=self._remove_folder).pack(side="left")

        self.watch_status_var = tk.StringVar()
        self.watch_status_lbl = tk.Label(body, textvariable=self.watch_status_var,
                                         font=("Segoe UI", 8), anchor="w")
        self.watch_status_lbl.pack(anchor="w", pady=(4, 0))

        ttk.Separator(body, orient="horizontal").pack(fill="x", pady=12)

        # ── Dump Folder ──
        tk.Label(body, text="Dump Folder",
                 font=("Segoe UI", 9, "bold"), anchor="w").pack(anchor="w")
        tk.Label(body,
                 text="Renamed files are moved here under Building \\ Level \\ Area.",
                 font=("Segoe UI", 8), fg="#666", anchor="w").pack(anchor="w", pady=(0, 8))

        dump_row = tk.Frame(body)
        dump_row.pack(fill="x")
        self.dump_entry = tk.Entry(dump_row, textvariable=self._dump_folder,
                                   font=("Consolas", 9), width=44)
        self.dump_entry.pack(side="left", fill="x", expand=True, ipady=4)
        tk.Button(dump_row, text="Browse…",
                  font=("Segoe UI", 9), relief="flat", bg="#e8edf2",
                  cursor="hand2", padx=8, pady=4,
                  command=self._browse_dump).pack(side="left", padx=(6, 0))

        self.dump_status_var = tk.StringVar()
        self.dump_status_lbl = tk.Label(body, textvariable=self.dump_status_var,
                                        font=("Segoe UI", 8), anchor="w")
        self.dump_status_lbl.pack(anchor="w", pady=(4, 0))
        self._dump_folder.trace_add("write", lambda *_: self._check_dump_folder())
        self._check_dump_folder()

        ttk.Separator(body, orient="horizontal").pack(fill="x", pady=12)

        tk.Button(body, text="  Start Watching  ",
                  font=("Segoe UI", 11, "bold"),
                  bg="#1a3a5c", fg="white",
                  activebackground="#2a5a8c", activeforeground="white",
                  relief="flat", cursor="hand2", padx=12, pady=6,
                  command=self._start).pack(anchor="e")

    def _refresh_list(self):
        self.listbox.delete(0, tk.END)
        for f in self._folders:
            self.listbox.insert(tk.END, f"  {f}")
        self._update_watch_status()

    def _update_watch_status(self):
        if not self._folders:
            self.watch_status_var.set("⚠  No folders configured")
            self.watch_status_lbl.config(fg="#b87a00")
            return
        missing = [f for f in self._folders if not Path(f).exists()]
        if missing:
            self.watch_status_var.set(f"⚠  {len(missing)} folder(s) not found — will be created on start")
            self.watch_status_lbl.config(fg="#b87a00")
        else:
            self.watch_status_var.set(f"✔  {len(self._folders)} folder(s) configured")
            self.watch_status_lbl.config(fg="#2a7a2a")

    def _check_dump_folder(self):
        path = Path(self._dump_folder.get())
        if path.exists():
            self.dump_status_var.set("✔  Folder exists")
            self.dump_status_lbl.config(fg="#2a7a2a")
        else:
            self.dump_status_var.set("⚠  Folder not found — will be created automatically")
            self.dump_status_lbl.config(fg="#b87a00")

    def _add_folder(self):
        initial = self._folders[-1] if self._folders else str(Path.home())
        if not Path(initial).exists():
            initial = str(Path.home())
        chosen = filedialog.askdirectory(title="Select TFLX Watch Folder",
                                         initialdir=initial, parent=self.root)
        if chosen:
            path = chosen.replace("/", "\\")
            if path not in self._folders:
                self._folders.append(path)
                self._refresh_list()

    def _remove_folder(self):
        sel = self.listbox.curselection()
        if not sel:
            messagebox.showinfo("Nothing Selected", "Click a folder in the list first.", parent=self.root)
            return
        idx = sel[0]
        folder = self._folders[idx]
        if messagebox.askyesno("Remove Folder", f"Remove this folder?\n\n{folder}", parent=self.root):
            self._folders.pop(idx)
            self._refresh_list()

    def _browse_dump(self):
        current = self._dump_folder.get()
        initial = current if Path(current).exists() else str(Path.home())
        chosen = filedialog.askdirectory(title="Select Dump Folder",
                                         initialdir=initial, parent=self.root)
        if chosen:
            self._dump_folder.set(chosen.replace("/", "\\"))

    def _start(self):
        if not self._folders:
            messagebox.showwarning("No Folders", "Add at least one watch folder.", parent=self.root)
            return
        dump = self._dump_folder.get().strip()
        if not dump:
            messagebox.showwarning("No Dump Folder", "Please set a dump folder.", parent=self.root)
            return
        save_config({"watch_folders": self._folders, "dump_folder": dump})
        self.root.withdraw()
        WatcherApp(self.root, self._folders, dump).run()

    def _center(self):
        self.root.update_idletasks()
        w, h = self.root.winfo_width(), self.root.winfo_height()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")


# ── Rename popup ──────────────────────────────────────────────────────────────

class RenamePopup(tk.Toplevel):
    def __init__(self, parent, filepath, dump_folder, on_done):
        super().__init__(parent)
        self.filepath    = filepath
        self.dump_folder = Path(dump_folder)
        self.on_done     = on_done
        self._timestamp  = datetime.now().strftime("%m%d%y_%H%M")

        self.title("TFLX File Detected")
        self.resizable(False, False)
        self.grab_set()
        self.attributes("-topmost", True)
        self.focus_force()

        self.building_var    = tk.StringVar(value="DG")
        self.level_var       = tk.StringVar(value="UG")
        self.area_var        = tk.StringVar(value="Tower")
        self.tablet_var      = tk.StringVar(value="T1")
        self.preview_var     = tk.StringVar()
        self.dest_path_var   = tk.StringVar()

        self._build_ui()
        self._update_preview()

        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    def _build_ui(self):
        hdr = tk.Frame(self, bg="#1a3a5c")
        hdr.pack(fill="x")
        tk.Label(hdr, text="  New TFLX File Detected",
                 bg="#1a3a5c", fg="white",
                 font=("Segoe UI", 11, "bold"),
                 pady=10, padx=12).pack(anchor="w")

        body = tk.Frame(self, padx=14, pady=10)
        body.pack(fill="both", expand=True)

        tk.Label(body, text="Detected file:", font=("Segoe UI", 9, "bold"),
                 anchor="w").grid(row=0, column=0, columnspan=4, sticky="w")
        tk.Label(body, text=self.filepath.name,
                 font=("Consolas", 9), fg="#555",
                 wraplength=420, anchor="w").grid(
                 row=1, column=0, columnspan=4, sticky="w", pady=(0, 10))

        ttk.Separator(body, orient="horizontal").grid(
            row=2, column=0, columnspan=4, sticky="ew", pady=(0, 10))

        for col, label in enumerate(["Building", "Level", "Area", "Tablet"]):
            tk.Label(body, text=label, font=("Segoe UI", 9, "bold"),
                     anchor="w").grid(row=3, column=col, sticky="w",
                                      padx=(0 if col == 0 else 14, 0))

        bld_frame = tk.Frame(body)
        bld_frame.grid(row=4, column=0, sticky="nw", pady=(4, 0))
        for b in BUILDINGS:
            tk.Radiobutton(bld_frame, text=b, variable=self.building_var,
                           value=b, font=("Segoe UI", 10),
                           command=self._on_building_change).pack(anchor="w")

        self.level_cb = ttk.Combobox(body, textvariable=self.level_var,
                                     values=LEVELS, state="readonly", width=7)
        self.level_cb.grid(row=4, column=1, sticky="nw", padx=(14, 0), pady=(4, 0))
        self.level_cb.bind("<<ComboboxSelected>>", lambda _: self._update_preview())

        self.area_cb = ttk.Combobox(body, textvariable=self.area_var,
                                    values=AREAS, state="readonly", width=9)
        self.area_cb.grid(row=4, column=2, sticky="nw", padx=(14, 0), pady=(4, 0))
        self.area_cb.bind("<<ComboboxSelected>>", lambda _: self._update_preview())

        tab_frame = tk.Frame(body)
        tab_frame.grid(row=4, column=3, sticky="nw", padx=(14, 0), pady=(4, 0))
        for t in TABLETS:
            tk.Radiobutton(tab_frame, text=t, variable=self.tablet_var,
                           value=t, font=("Segoe UI", 10),
                           command=self._update_preview).pack(anchor="w")

        # Timestamp
        ttk.Separator(body, orient="horizontal").grid(
            row=5, column=0, columnspan=4, sticky="ew", pady=(14, 8))
        ts_frame = tk.Frame(body)
        ts_frame.grid(row=6, column=0, columnspan=4, sticky="w")
        tk.Label(ts_frame, text="Timestamp:",
                 font=("Segoe UI", 9, "bold")).pack(side="left")
        tk.Label(ts_frame, text=f"  {self._timestamp}  (captured at popup open)",
                 font=("Consolas", 9), fg="#555").pack(side="left")

        # Preview filename
        ttk.Separator(body, orient="horizontal").grid(
            row=7, column=0, columnspan=4, sticky="ew", pady=(10, 6))
        tk.Label(body, text="New filename:", font=("Segoe UI", 9, "bold"),
                 anchor="w").grid(row=8, column=0, columnspan=4, sticky="w")
        tk.Label(body, textvariable=self.preview_var,
                 font=("Consolas", 11, "bold"), fg="#1a3a5c").grid(
                 row=9, column=0, columnspan=4, sticky="w", pady=(2, 6))

        # Destination path
        tk.Label(body, text="Destination:", font=("Segoe UI", 9, "bold"),
                 anchor="w").grid(row=10, column=0, columnspan=4, sticky="w")
        tk.Label(body, textvariable=self.dest_path_var,
                 font=("Consolas", 8), fg="#555",
                 wraplength=420, anchor="w").grid(
                 row=11, column=0, columnspan=4, sticky="w", pady=(2, 10))

        # Buttons
        btn_frame = tk.Frame(body)
        btn_frame.grid(row=12, column=0, columnspan=4, sticky="e", pady=(4, 0))
        tk.Button(btn_frame, text="Skip (keep original name)",
                  font=("Segoe UI", 9), fg="#666", relief="flat",
                  cursor="hand2", command=self._skip).pack(side="left", padx=(0, 8))
        tk.Button(btn_frame, text="  Rename & Move  ",
                  font=("Segoe UI", 10, "bold"),
                  bg="#1a3a5c", fg="white",
                  activebackground="#2a5a8c", activeforeground="white",
                  relief="flat", cursor="hand2", padx=10, pady=4,
                  command=self._rename).pack(side="left")

    def _on_building_change(self):
        if self.building_var.get() == "SSB":
            self.area_cb.configure(state="disabled")
            self.area_var.set("")
        else:
            self.area_cb.configure(state="readonly")
            if not self.area_var.get():
                self.area_var.set("Tower")
        self._update_preview()

    def _build_new_name(self):
        building = self.building_var.get()
        level    = self.level_var.get()
        area     = self.area_var.get()
        tablet   = self.tablet_var.get()
        ts       = self._timestamp
        if building == "DG" and area:
            return f"{building}-{level}-{area}-{tablet}-{ts}.tflx"
        return f"{building}-{level}-{tablet}-{ts}.tflx"

    def _build_dest_path(self):
        """Returns the full destination folder path in the dump directory."""
        building = self.building_var.get()
        level    = self.level_var.get()
        area     = self.area_var.get()
        if building == "DG" and area:
            return self.dump_folder / building / level / area
        return self.dump_folder / building / level

    def _update_preview(self):
        new_name  = self._build_new_name()
        dest_dir  = self._build_dest_path()
        self.preview_var.set(new_name)
        self.dest_path_var.set(str(dest_dir / new_name))

    def _rename(self):
        new_name = self._build_new_name()
        dest_dir = self._build_dest_path()
        dest_path = dest_dir / new_name

        if dest_path.exists():
            if not messagebox.askyesno("File Exists",
                    f"'{new_name}' already exists in the destination.\nOverwrite it?",
                    parent=self):
                return

        # Create folder structure if needed
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            messagebox.showerror("Folder Error",
                f"Could not create destination folder:\n{dest_dir}\n\n{e}", parent=self)
            return

        # Move to dump folder with new name
        try:
            shutil.move(str(self.filepath), str(dest_path))
            print(f"[Moved]    {self.filepath.name}  ->  {dest_path}")
        except OSError as e:
            messagebox.showerror("Copy Failed", str(e), parent=self)
            return

        messagebox.showinfo("Done",
            f"File moved to:\n\n{dest_path}", parent=self)

        self.on_done(renamed=True)
        self.destroy()

    def _skip(self):
        print(f"[Skipped]  {self.filepath.name}")
        self.on_done(renamed=False)
        self.destroy()


# ── Main watcher app ──────────────────────────────────────────────────────────

class WatcherApp:
    def __init__(self, root: tk.Tk, watch_folders: list, dump_folder: str):
        self.root          = root
        self.watch_folders = watch_folders
        self.dump_folder   = dump_folder
        self._file_queue   = queue.Queue()
        self._popup_open   = False
        self._start_observers()
        self._poll_queue()

    def _start_observers(self):
        handler = TFLXHandler(self._file_queue)
        for folder in self.watch_folders:
            watch_path = Path(folder)
            watch_path.mkdir(parents=True, exist_ok=True)
            observer = Observer()
            observer.schedule(handler, str(watch_path), recursive=True)
            observer.daemon = True
            observer.start()
            print(f"[Watching] {watch_path}")

    def _poll_queue(self):
        if not self._popup_open:
            try:
                filepath = self._file_queue.get_nowait()
                self._popup_open = True
                answer = messagebox.askyesno(
                    "New TFLX File Detected",
                    f"New file detected:\n\n{filepath.name}\n\nWould you like to rename and move it?",
                )
                if answer:
                    RenamePopup(self.root, filepath, self.dump_folder,
                                on_done=lambda renamed: self._on_popup_done())
                else:
                    print(f"[Ignored]  {filepath.name}")
                    self._on_popup_done()
            except queue.Empty:
                pass
        self.root.after(500, self._poll_queue)

    def _on_popup_done(self):
        self._popup_open = False

    def run(self):
        self.root.mainloop()


# ── Entry point ───────────────────────────────────────────────────────────────

def check_dependencies():
    try:
        import watchdog  # noqa: F401
    except ImportError:
        print("watchdog is not installed.\nRun:  pip install watchdog")
        sys.exit(1)


if __name__ == "__main__":
    check_dependencies()
    import queue
    root = tk.Tk()
    root.withdraw()
    LauncherWindow(root)
    root.mainloop()
