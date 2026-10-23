#!/usr/bin/env python3
"""
AIVISRA Virtual CCTV & Enterprise NVR RTSP Generator
===================================================
Simulates real enterprise CCTV cameras & NVR (e.g. Hikvision / Dahua / Axis)
for low-latency testing of AIVISRA StreamCore.

Supports:
- Enterprise NVR In-Memory Proxy Mode (Zero lag, 1 master publisher -> N RTSP streams)
- Multi-Video Customization (Assign different videos to different cameras or load from folder)
- CCTV Standard Encoding (-tune zerolatency, -bf 0, fixed GOP, steady 25 FPS clock)
- Cross-platform: Runs on Linux & Windows (GUI and Headless CLI mode)
"""

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

# Tkinter is imported conditionally for headless / CLI support
try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    HAS_TK = True
except ImportError:
    HAS_TK = False

APP_DIR = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parent
)
BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))
TOOLS_DIR = APP_DIR / "tools"
BUNDLED_TOOLS_DIR = BUNDLE_DIR / "tools"
LOG_DIR = APP_DIR / "logs"
CONFIG_PATH = APP_DIR / "mediamtx.yml"


def get_lan_ip():
    """Detect LAN IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"


def find_tool(name):
    """Find binary on Windows or Linux."""
    ext = ".exe" if os.name == "nt" else ""
    for folder in (BUNDLED_TOOLS_DIR, TOOLS_DIR):
        p = folder / (name + ext)
        if p.exists():
            return str(p)
        if not ext and (folder / name).exists():
            return str(folder / name)
    from shutil import which
    return which(name + ext) or which(name)


class NvrServer:
    """Core RTSP server engine handling MediaMTX and FFmpeg publishers."""

    def __init__(self):
        self.procs = []
        self.logs = []
        self.server = None
        self.server_log = None
        self.running = False
        self.master_urls = {}

    def start(self, camera_mappings, port=8554, lan_ip=None, mode="copy",
              fps=25, bitrate="2M", use_nvr_proxy=True):
        """
        camera_mappings: dict of {camera_id: video_path}
        e.g. {'cam001': '/path/to/vid1.mp4', 'cam002': '/path/to/vid2.mp4'}
        """
        if self.running:
            return

        ff = find_tool("ffmpeg")
        mt = find_tool("mediamtx")
        if not ff:
            raise RuntimeError(f"FFmpeg not found. Put ffmpeg{' .exe' if os.name == 'nt' else ''} in tools/ or install on system.")
        if not mt:
            raise RuntimeError(f"MediaMTX not found. Put mediamtx{' .exe' if os.name == 'nt' else ''} in tools/.")

        # Validate video files
        for cid, vpath in camera_mappings.items():
            p = Path(vpath)
            if not p.exists():
                raise FileNotFoundError(f"Video file not found for {cid}: {vpath}")

        lan_ip = lan_ip or get_lan_ip()
        LOG_DIR.mkdir(parents=True, exist_ok=True)

        # Unique videos mapped to distinct master sources
        # video_path -> master_source_id (e.g. "src001")
        unique_videos = {}
        for cid, vpath in camera_mappings.items():
            resolved = str(Path(vpath).resolve())
            if resolved not in unique_videos:
                unique_videos[resolved] = f"src{len(unique_videos)+1:03d}"

        # Generate MediaMTX configuration
        # If use_nvr_proxy is enabled, MediaMTX proxies camera paths in-memory from the masters
        config_lines = [
            "# AIVISRA Enterprise Virtual NVR Configuration",
            "rtsp: yes",
            f"rtspAddress: :{port}",
            "rtspTransports: [tcp]",
            "",
            "rtmp: no",
            "hls: no",
            "srt: no",
            "",
            "api: yes",
            "apiAddress: 127.0.0.1:9997",
            "",
            "webrtc: yes",
            "webrtcAddress: :8889",
            "webrtcLocalUDPAddress: :8189",
            f"webrtcAdditionalHosts: [{lan_ip}]",
            "",
            "paths:",
        ]

        if use_nvr_proxy:
            # Register master publisher paths
            for vpath, src_id in unique_videos.items():
                config_lines.append(f"  {src_id}:")
            # Map each camera path as an in-memory proxy of its assigned master source
            for cid, vpath in camera_mappings.items():
                src_id = unique_videos[str(Path(vpath).resolve())]
                config_lines.append(f"  {cid}:")
                config_lines.append(f"    source: rtsp://127.0.0.1:{port}/{src_id}")
                config_lines.append("    sourceOnDemand: yes")
        else:
            # Direct publishers (no proxying)
            for cid in camera_mappings:
                config_lines.append(f"  {cid}:")

        CONFIG_PATH.write_text("\n".join(config_lines) + "\n", encoding="utf-8")

        # Start MediaMTX
        self.server_log = open(LOG_DIR / "mediamtx.log", "w", encoding="utf-8", errors="ignore")
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        self.server = subprocess.Popen(
            [mt, str(CONFIG_PATH)],
            cwd=str(APP_DIR),
            stdin=subprocess.DEVNULL,
            stdout=self.server_log,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
        )
        time.sleep(1.0)
        if self.server.poll() is not None:
            raise RuntimeError("MediaMTX failed to start. Check logs/mediamtx.log for details.")

        # Start FFmpeg publishers
        # If NVR proxy: publish each unique video ONCE to its master source
        # If direct: publish to each camera URL directly
        publish_targets = {}
        if use_nvr_proxy:
            for vpath, src_id in unique_videos.items():
                target_url = f"rtsp://127.0.0.1:{port}/{src_id}"
                publish_targets[src_id] = (vpath, target_url)
        else:
            for cid, vpath in camera_mappings.items():
                target_url = f"rtsp://127.0.0.1:{port}/{cid}"
                publish_targets[cid] = (vpath, target_url)

        for name, (vpath, url) in publish_targets.items():
            lf = open(LOG_DIR / f"{name}.log", "w", encoding="utf-8", errors="ignore")
            self.logs.append(lf)

            # Build real-time CCTV standard FFmpeg command
            cmd = [
                ff, "-hide_banner", "-loglevel", "warning",
                "-re", "-stream_loop", "-1", "-i", str(vpath), "-an"
            ]

            if mode == "copy":
                cmd += ["-c:v", "copy"]
            else:
                br = bitrate.strip() or "2M"
                cmd += [
                    "-vf", f"fps={fps}",
                    "-c:v", "libx264",
                    "-preset", "ultrafast",
                    "-tune", "zerolatency",
                    "-bf", "0",              # Zero B-frames: Essential for zero-latency CCTV
                    "-g", str(max(1, fps)),  # 1 keyframe every second (standard CCTV GOP)
                    "-pix_fmt", "yuv420p",
                    "-b:v", br,
                    "-maxrate", br,
                    "-bufsize", "2M",
                ]

            cmd += ["-f", "rtsp", "-rtsp_transport", "tcp", url]

            proc = subprocess.Popen(
                cmd,
                cwd=str(APP_DIR),
                stdin=subprocess.DEVNULL,
                stdout=lf,
                stderr=subprocess.STDOUT,
                creationflags=creationflags,
            )
            self.procs.append(proc)
            time.sleep(0.05)

        self.running = True

    def stop(self):
        """Stop all publishers and MediaMTX server."""
        for p in self.procs:
            try:
                if p.poll() is None:
                    p.terminate()
            except Exception:
                pass
        time.sleep(0.3)
        for p in self.procs:
            try:
                if p.poll() is None:
                    p.kill()
            except Exception:
                pass
        self.procs = []

        if self.server:
            try:
                if self.server.poll() is None:
                    self.server.terminate()
            except Exception:
                pass
            time.sleep(0.2)
            try:
                if self.server.poll() is None:
                    self.server.kill()
            except Exception:
                pass
            self.server = None

        for f in self.logs:
            try:
                f.close()
            except Exception:
                pass
        self.logs = []

        if self.server_log:
            try:
                self.server_log.close()
            except Exception:
                pass
            self.server_log = None

        self.running = False

    def status(self):
        alive_publishers = sum(1 for p in self.procs if p.poll() is None)
        server_ok = self.server is not None and self.server.poll() is None
        return {
            "running": self.running,
            "alive_publishers": alive_publishers,
            "total_publishers": len(self.procs),
            "mediamtx_online": server_ok,
        }


class App:
    """Tkinter Graphical User Interface for Windows & Linux Desktop."""

    def __init__(self, root):
        self.root = root
        self.root.title("AIVISRA Virtual CCTV & Enterprise NVR Generator")
        self.root.geometry("1020x760")
        self.root.minsize(900, 680)

        self.server = NvrServer()
        self.single_video = tk.StringVar()
        self.video_folder = tk.StringVar()
        self.nvr_mode = tk.StringVar(value="proxy")  # "proxy" (single/shared) or "custom" (multi-video)
        self.count = tk.IntVar(value=10)
        self.port = tk.IntVar(value=8554)
        self.prefix = tk.StringVar(value="cam")
        self.ip = tk.StringVar(value=get_lan_ip())
        self.mode = tk.StringVar(value="copy")  # "copy" or "transcode"
        self.fps = tk.IntVar(value=25)
        self.bitrate = tk.StringVar(value="2M")
        self.status_text = tk.StringVar(value="Stopped")

        # Camera ID -> Video File Path mapping dictionary
        self.camera_mapping = {}

        self.build()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.poll()

    def build(self):
        main = ttk.Frame(self.root, padding=14)
        main.pack(fill="both", expand=True)

        # Header
        head = ttk.Frame(main)
        head.pack(fill="x", pady=(0, 10))
        ttk.Label(head, text="AIVISRA Virtual CCTV & Enterprise NVR",
                  font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(head, text="Simulates enterprise NVR (Hikvision/Dahua) with in-memory stream proxying and zero lag for StreamCore testing.",
                  font=("Segoe UI", 9), foreground="#555555").pack(anchor="w")

        # Setup Notebook (Tabs)
        tabs = ttk.Notebook(main)
        tabs.pack(fill="x", pady=(0, 10))

        # Tab 1: Video & NVR Setup
        tab_setup = ttk.Frame(tabs, padding=10)
        tabs.add(tab_setup, text=" Stream & Camera Configuration ")

        # Mode Selection
        mode_box = ttk.LabelFrame(tab_setup, text="NVR Operating Mode", padding=8)
        mode_box.pack(fill="x", pady=(0, 8))

        ttk.Radiobutton(
            mode_box,
            text="Enterprise NVR Proxy Mode (Recommended: 1 Video Master -> N Cameras In-Memory Proxy, Zero Lag)",
            variable=self.nvr_mode, value="proxy", command=self.on_mode_change
        ).pack(anchor="w", pady=2)

        ttk.Radiobutton(
            mode_box,
            text="Multi-Video Custom Mode (Assign different videos to different cameras or folder auto-cycle)",
            variable=self.nvr_mode, value="custom", command=self.on_mode_change
        ).pack(anchor="w", pady=2)

        # Video selection frame
        vbox = ttk.LabelFrame(tab_setup, text="Video Source", padding=8)
        vbox.pack(fill="x", pady=(0, 8))

        # Single video row
        self.row_single = ttk.Frame(vbox)
        self.row_single.pack(fill="x", pady=2)
        ttk.Label(self.row_single, text="Single Video File:", width=18).pack(side="left")
        ttk.Entry(self.row_single, textvariable=self.single_video).pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(self.row_single, text="Browse File...", command=self.browse_single_video).pack(side="left")

        # Folder row
        self.row_folder = ttk.Frame(vbox)
        self.row_folder.pack(fill="x", pady=2)
        ttk.Label(self.row_folder, text="Video Folder (Multi):", width=18).pack(side="left")
        ttk.Entry(self.row_folder, textvariable=self.video_folder).pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(self.row_folder, text="Browse Folder...", command=self.browse_folder).pack(side="left")
        ttk.Button(self.row_folder, text="Auto-Assign Folder", command=self.auto_assign_folder).pack(side="left", padx=(4, 0))

        # Parameters Frame
        pbox = ttk.LabelFrame(tab_setup, text="Camera & Network Settings", padding=8)
        pbox.pack(fill="x", pady=(0, 8))

        r1 = ttk.Frame(pbox)
        r1.pack(fill="x", pady=3)
        ttk.Label(r1, text="Virtual Cameras:").pack(side="left")
        ttk.Spinbox(r1, from_=1, to=100, textvariable=self.count, width=6, command=self.on_count_change).pack(side="left", padx=(4, 16))

        ttk.Label(r1, text="Path Prefix:").pack(side="left")
        ttk.Entry(r1, textvariable=self.prefix, width=8).pack(side="left", padx=(4, 16))

        ttk.Label(r1, text="RTSP Port:").pack(side="left")
        ttk.Entry(r1, textvariable=self.port, width=8).pack(side="left", padx=(4, 16))

        ttk.Label(r1, text="LAN IP:").pack(side="left")
        ttk.Entry(r1, textvariable=self.ip, width=16).pack(side="left", padx=(4, 4))
        ttk.Button(r1, text="Refresh IP", command=lambda: self.ip.set(get_lan_ip())).pack(side="left")

        # Transcoding Frame
        tbox = ttk.LabelFrame(tab_setup, text="Encoding Standard", padding=8)
        tbox.pack(fill="x")

        r2 = ttk.Frame(tbox)
        r2.pack(fill="x", pady=2)
        ttk.Radiobutton(r2, text="Stream copy (Low CPU, fastest, source must be H.264)",
                        variable=self.mode, value="copy").pack(side="left")
        ttk.Radiobutton(r2, text="CCTV Zero-Latency Transcode (H.264, -bf 0, GOP 25, constant 25 FPS)",
                        variable=self.mode, value="transcode").pack(side="left", padx=(20, 0))

        r3 = ttk.Frame(tbox)
        r3.pack(fill="x", pady=(4, 0))
        ttk.Label(r3, text="Target FPS:").pack(side="left")
        ttk.Entry(r3, textvariable=self.fps, width=6).pack(side="left", padx=(4, 16))
        ttk.Label(r3, text="Bitrate:").pack(side="left")
        ttk.Entry(r3, textvariable=self.bitrate, width=8).pack(side="left", padx=(4, 0))

        # Tab 2: Custom Camera-to-Video Mapping Table
        tab_custom = ttk.Frame(tabs, padding=10)
        tabs.add(tab_custom, text=" Camera-to-Video Mappings ")

        tree_frame = ttk.Frame(tab_custom)
        tree_frame.pack(fill="both", expand=True)

        cols = ("camera", "video")
        self.tree = ttk.Treeview(tree_frame, columns=cols, show="headings", height=8)
        self.tree.heading("camera", text="Camera ID / RTSP Path")
        self.tree.heading("video", text="Assigned Video File")
        self.tree.column("camera", width=140, anchor="w")
        self.tree.column("video", width=600, anchor="w")

        tree_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        tree_scroll.pack(side="right", fill="y")

        btn_row = ttk.Frame(tab_custom)
        btn_row.pack(fill="x", pady=(8, 0))
        ttk.Button(btn_row, text="Change Selected Camera's Video...", command=self.change_selected_video).pack(side="left")
        ttk.Button(btn_row, text="Set All to Single Video", command=self.set_all_to_single).pack(side="left", padx=8)

        # Control Action Buttons
        act = ttk.Frame(main)
        act.pack(fill="x", pady=(6, 8))
        self.start_btn = ttk.Button(act, text="Start RTSP Cameras", command=self.start)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(act, text="Stop", command=self.stop, state="disabled")
        self.stop_btn.pack(side="left", padx=8)

        ttk.Button(act, text="Copy URLs", command=self.copy_urls).pack(side="left", padx=(14, 0))
        ttk.Button(act, text="Save URLs.txt", command=self.save_urls).pack(side="left", padx=8)
        ttk.Button(act, text="Export StreamCore app.yaml", command=self.export_yaml).pack(side="left", padx=8)

        # Status Bar
        sbar = ttk.LabelFrame(main, text="Status", padding=6)
        sbar.pack(fill="x", pady=(0, 8))
        self.status_lbl = ttk.Label(sbar, textvariable=self.status_text, font=("Segoe UI", 10, "bold"), foreground="#1f6feb")
        self.status_lbl.pack(anchor="w")

        # RTSP Output Text Area
        ubox = ttk.LabelFrame(main, text="Generated RTSP & WebRTC URLs", padding=8)
        ubox.pack(fill="both", expand=True)
        self.txt = tk.Text(ubox, font=("Consolas", 9), wrap="none")
        self.txt.pack(fill="both", expand=True)

        for v in (self.count, self.port, self.prefix, self.ip):
            try:
                v.trace_add("write", lambda *_: self.refresh_mappings_and_urls())
            except Exception:
                pass

        self.on_mode_change()
        self.refresh_mappings_and_urls()

    def on_mode_change(self):
        """Toggle UI elements based on proxy vs custom mode."""
        self.refresh_mappings_and_urls()

    def on_count_change(self):
        self.refresh_mappings_and_urls()

    def browse_single_video(self):
        p = filedialog.askopenfilename(
            filetypes=[("Video", "*.mp4 *.mkv *.mov *.avi *.ts *.m4v"), ("All", "*.*")]
        )
        if p:
            self.single_video.set(p)
            self.refresh_mappings_and_urls()

    def browse_folder(self):
        d = filedialog.askdirectory()
        if d:
            self.video_folder.set(d)
            self.auto_assign_folder()

    def auto_assign_folder(self):
        d = self.video_folder.get().strip()
        if not d or not Path(d).is_dir():
            messagebox.showwarning("Folder", "Select a valid directory containing video files.")
            return

        exts = {".mp4", ".mkv", ".mov", ".avi", ".ts", ".m4v"}
        files = [str(f.resolve()) for f in sorted(Path(d).iterdir()) if f.suffix.lower() in exts]
        if not files:
            messagebox.showwarning("No Videos", "No video files found in the selected folder.")
            return

        cams = self.get_camera_ids()
        for idx, cid in enumerate(cams):
            self.camera_mapping[cid] = files[idx % len(files)]

        self.nvr_mode.set("custom")
        self.update_tree_view()
        self.refresh_urls()

    def change_selected_video(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Select Camera", "Please select a camera row in the table first.")
            return
        cid = self.tree.item(selected[0], "values")[0]
        p = filedialog.askopenfilename(
            title=f"Choose Video for {cid}",
            filetypes=[("Video", "*.mp4 *.mkv *.mov *.avi *.ts *.m4v"), ("All", "*.*")]
        )
        if p:
            self.camera_mapping[cid] = p
            self.nvr_mode.set("custom")
            self.update_tree_view()
            self.refresh_urls()

    def set_all_to_single(self):
        v = self.single_video.get().strip()
        if not v or not Path(v).exists():
            messagebox.showwarning("Select Video", "Please select a valid single video first.")
            return
        for cid in self.get_camera_ids():
            self.camera_mapping[cid] = v
        self.update_tree_view()
        self.refresh_urls()

    def get_camera_ids(self):
        try:
            n = max(1, int(self.count.get()))
        except Exception:
            n = 10
        pre = self.prefix.get().strip() or "cam"
        width = max(3, len(str(n)))
        return [f"{pre}{i:0{width}d}" for i in range(1, n + 1)]

    def refresh_mappings_and_urls(self):
        cams = self.get_camera_ids()
        default_vid = self.single_video.get().strip()

        # Update mapping dict
        new_map = {}
        for cid in cams:
            new_map[cid] = self.camera_mapping.get(cid) or default_vid
        self.camera_mapping = new_map

        self.update_tree_view()
        self.refresh_urls()

    def update_tree_view(self):
        if not hasattr(self, "tree"):
            return
        self.tree.delete(*self.tree.get_children())
        for cid, vpath in self.camera_mapping.items():
            self.tree.insert("", "end", values=(cid, vpath or "(None selected)"))

    def urls(self, local=False):
        cams = self.get_camera_ids()
        try:
            port = int(self.port.get())
        except Exception:
            port = 8554
        host = "127.0.0.1" if local else (self.ip.get().strip() or get_lan_ip())
        return [f"rtsp://{host}:{port}/{cid}" for cid in cams]

    def refresh_urls(self):
        if not hasattr(self, "txt"):
            return
        cams = self.get_camera_ids()
        host = self.ip.get().strip() or get_lan_ip()
        port = self.port.get()

        lines = ["# --- RTSP CAMERA URLS (Use in StreamCore or VLC) ---"]
        for cid in cams:
            vname = Path(self.camera_mapping.get(cid, "")).name or "no-file"
            lines.append(f"rtsp://{host}:{port}/{cid}  # [{cid}] -> {vname}")

        lines.append("\n# --- WEBRTC LIVE STREAM URLS (Open in Chrome/Firefox) ---")
        for cid in cams:
            lines.append(f"http://{host}:8889/{cid}/")

        self.txt.delete("1.0", "end")
        self.txt.insert("1.0", "\n".join(lines))

    def copy_urls(self):
        t = "\n".join(self.urls())
        self.root.clipboard_clear()
        self.root.clipboard_append(t)
        self.status_text.set(f"Copied {len(self.urls())} RTSP URLs to clipboard!")

    def save_urls(self):
        p = filedialog.asksaveasfilename(defaultextension=".txt", initialfile="rtsp_urls.txt")
        if p:
            Path(p).write_text("\n".join(self.urls()) + "\n", encoding="utf-8")
            self.status_text.set(f"Saved URLs to {Path(p).name}")

    def export_yaml(self):
        """Export cameras section formatted for StreamCore app.yaml."""
        p = filedialog.asksaveasfilename(defaultextension=".yaml", initialfile="streamcore_cameras.yaml")
        if not p:
            return

        cams = self.get_camera_ids()
        host = self.ip.get().strip() or get_lan_ip()
        port = self.port.get()

        out = ["cameras:"]
        for cid in cams:
            out.append(f"  - id: {cid.upper()}")
            out.append(f"    uri: rtsp://{host}:{port}/{cid}")
            out.append("    codec: h264")
            out.append("    decoder: nvh264dec")
            out.append("    enabled: true")
            out.append("    expected_fps: 25.0")
            out.append(f"    live_path: {cid}")

        Path(p).write_text("\n".join(out) + "\n", encoding="utf-8")
        messagebox.showinfo("Exported", f"Saved StreamCore camera configuration to {p}")

    def start(self):
        if self.server.running:
            return

        # Ensure all cameras have valid video assigned
        for cid, vpath in self.camera_mapping.items():
            if not vpath or not Path(vpath).exists():
                messagebox.showerror("Missing Video", f"Camera {cid} has no valid video assigned.\nPlease select a video file or folder.")
                return

        try:
            port = int(self.port.get())
            fps = int(self.fps.get())
        except Exception:
            messagebox.showerror("Invalid Input", "Check port and FPS values.")
            return

        use_proxy = (self.nvr_mode.get() == "proxy")

        try:
            self.server.start(
                camera_mappings=self.camera_mapping,
                port=port,
                lan_ip=self.ip.get().strip() or get_lan_ip(),
                mode=self.mode.get(),
                fps=fps,
                bitrate=self.bitrate.get().strip() or "2M",
                use_nvr_proxy=use_proxy,
            )
            self.start_btn.config(state="disabled")
            self.stop_btn.config(state="normal")
            self.status_lbl.config(foreground="#3fb950")
        except Exception as exc:
            self.server.stop()
            messagebox.showerror("Start Failed", str(exc))

    def stop(self):
        self.server.stop()
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.status_lbl.config(foreground="#d29922")
        self.status_text.set("Stopped")

    def poll(self):
        if self.server.running:
            st = self.server.status()
            mode_desc = "NVR In-Memory Proxy (Zero Lag)" if self.nvr_mode.get() == "proxy" else "Multi-Video Direct"
            self.status_text.set(
                f"Running: {st['alive_publishers']}/{st['total_publishers']} publishers | "
                f"MediaMTX: {'ONLINE' if st['mediamtx_online'] else 'OFFLINE'} | "
                f"Mode: {mode_desc} | Port: {self.port.get()}"
            )
        self.root.after(1500, self.poll)

    def close(self):
        self.stop()
        self.root.destroy()


def run_cli(args):
    """Headless CLI server runner for Linux or automated scripts."""
    print("=" * 64)
    print("AIVISRA Enterprise Virtual NVR RTSP Server (CLI Mode)")
    print("=" * 64)

    server = NvrServer()
    camera_mapping = {}

    count = args.count
    prefix = args.prefix
    width = max(3, len(str(count)))
    cam_ids = [f"{prefix}{i:0{width}d}" for i in range(1, count + 1)]

    # Determine video assignments
    if args.folder:
        folder = Path(args.folder)
        if not folder.is_dir():
            print(f"Error: Video folder does not exist: {args.folder}")
            return 1
        exts = {".mp4", ".mkv", ".mov", ".avi", ".ts", ".m4v"}
        files = [str(f.resolve()) for f in sorted(folder.iterdir()) if f.suffix.lower() in exts]
        if not files:
            print(f"Error: No video files found in {args.folder}")
            return 1
        for idx, cid in enumerate(cam_ids):
            camera_mapping[cid] = files[idx % len(files)]
    elif args.video:
        vid = Path(args.video).resolve()
        if not vid.exists():
            print(f"Error: Video file does not exist: {args.video}")
            return 1
        for cid in cam_ids:
            camera_mapping[cid] = str(vid)
    else:
        print("Error: Specify either --video <path> or --folder <path>")
        return 1

    lan_ip = args.ip or get_lan_ip()
    use_proxy = not args.no_proxy

    print(f"Cameras: {count}")
    print(f"Mode: {'Enterprise NVR In-Memory Proxy (Zero Lag)' if use_proxy else 'Direct Multi-Publisher'}")
    print(f"Encoding: {args.mode.upper()}")
    print(f"RTSP Port: {args.port}")
    print(f"LAN IP: {lan_ip}")
    print("-" * 64)

    try:
        server.start(
            camera_mappings=camera_mapping,
            port=args.port,
            lan_ip=lan_ip,
            mode=args.mode,
            fps=args.fps,
            bitrate=args.bitrate,
            use_nvr_proxy=use_proxy,
        )
    except Exception as exc:
        print(f"Failed to start NVR server: {exc}")
        return 1

    print("\nActive RTSP URLs:")
    for cid in cam_ids:
        print(f"  rtsp://{lan_ip}:{args.port}/{cid}  ->  {Path(camera_mapping[cid]).name}")

    print(f"\nWebRTC Preview: http://{lan_ip}:8889/<cam_id>/")
    print("\nServer running. Press Ctrl+C to stop.")

    def handle_sig(sig, frame):
        print("\nStopping NVR Server...")
        server.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_sig)
    signal.signal(signal.SIGTERM, handle_sig)

    while True:
        time.sleep(2)
        st = server.status()
        if not st["mediamtx_online"]:
            print("Warning: MediaMTX exited!")
            break


def main():
    parser = argparse.ArgumentParser(description="AIVISRA Virtual CCTV & Enterprise NVR RTSP Generator")
    parser.add_argument("--cli", action="store_true", help="Run headlessly in terminal (no GUI)")
    parser.add_argument("--video", type=str, help="Video file path for single/master stream")
    parser.add_argument("--folder", type=str, help="Folder containing video files to cycle across cameras")
    parser.add_argument("--count", type=int, default=10, help="Number of virtual RTSP cameras (default: 10)")
    parser.add_argument("--port", type=int, default=8554, help="RTSP Port (default: 8554)")
    parser.add_argument("--prefix", type=str, default="cam", help="Camera path prefix (default: cam)")
    parser.add_argument("--ip", type=str, help="LAN IP address override")
    parser.add_argument("--mode", choices=("copy", "transcode"), default="copy", help="Encoding mode (default: copy)")
    parser.add_argument("--fps", type=int, default=25, help="Transcode FPS (default: 25)")
    parser.add_argument("--bitrate", type=str, default="2M", help="Transcode bitrate (default: 2M)")
    parser.add_argument("--no-proxy", action="store_true", help="Disable MediaMTX in-memory proxying (run separate FFmpeg per stream)")
    args = parser.parse_args()

    # If --cli requested or headless environment without DISPLAY, run CLI
    is_headless = not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY") and os.name != "nt"
    if args.cli or is_headless:
        if not args.video and not args.folder:
            if is_headless and not HAS_TK:
                print("Headless Linux detected (no DISPLAY). Provide --video or --folder to start CLI mode.")
                print("Example: python3 app.py --cli --video cafe.mp4 --count 10")
                return 1
        return run_cli(args)

    if not HAS_TK:
        print("Error: Tkinter is not installed on this system.")
        print("Run with --cli flag or install python3-tk: sudo apt-get install python3-tk")
        return 1

    try:
        root = tk.Tk()
        app = App(root)
        root.mainloop()
        return 0
    except Exception as exc:
        import traceback
        err_msg = traceback.format_exc()
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            (LOG_DIR / "crash.log").write_text(err_msg, encoding="utf-8")
        except Exception:
            pass
        try:
            messagebox.showerror("Fatal Error", f"AIVISRA Virtual CCTV failed to start:\n\n{exc}\n\nSee logs/crash.log")
        except Exception:
            print(f"Fatal error:\n{err_msg}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
