"""
Local Network QR File Sharer — Premium Desktop GUI Application
--------------------------------------------------------------
A futuristic, dark-themed, glassmorphism-inspired desktop app 
built with CustomTkinter & Pillow.
"""

import customtkinter as ctk
from tkinter import filedialog, messagebox
import qrcode
from PIL import Image, ImageTk
import socket
import socketserver
import http.server
import os
import sys
import threading
import urllib.parse
import html
import mimetypes

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass


# ─── Helpers ───────────────────────────────────────────────────────────────

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def human_size(n_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n_bytes < 1024:
            return f"{n_bytes:.1f} {unit}"
        n_bytes /= 1024
    return f"{n_bytes:.1f} PB"


def get_file_icon(filename: str) -> str:
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    icons = {
        "pdf": "📄", "doc": "📝", "docx": "📝", "txt": "📝", "md": "📝",
        "jpg": "🖼️", "jpeg": "🖼️", "png": "🖼️", "gif": "🖼️", "svg": "🖼️",
        "mp4": "🎬", "mkv": "🎬", "avi": "🎬", "mov": "🎬",
        "mp3": "🎵", "wav": "🎵", "flac": "🎵",
        "zip": "📦", "rar": "📦", "7z": "📦",
        "py": "🐍", "js": "📜", "ts": "📜", "jsx": "⚛️", "tsx": "⚛️", 
        "html": "🌐", "css": "🎨", "scss": "🎨", "json": "⚙️", "xml": "⚙️",
        "php": "🐘", "java": "☕", "cpp": "⚙️", "c": "⚙️", "cs": "⚙️",
        "rb": "💎", "go": "🐹", "rs": "🦀", "sh": "💻", "bat": "💻",
        "sql": "🗄️", "db": "🗄️", "env": "🔒",
        "exe": "⚙️", "xls": "📊", "xlsx": "📊", "csv": "📊",
        "ppt": "📊", "pptx": "📊",
    }
    return icons.get(ext, "📁")


# The page markup and its CSS used to live inline in this file as one big
# triple-quoted string. They're now separate files sitting right next to
# gui.py: index.html (page skeleton, filled in with .format()) and style.css
# (served over HTTP as /style.css).
APP_DIR = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(APP_DIR, "index.html"), encoding="utf-8") as _f:
    HTML_TEMPLATE = _f.read()


# ─── HTTP Handler ───────────────────────────────────────────────────────────

class FileShareHandler(http.server.SimpleHTTPRequestHandler):
    shared_root = "."

    def do_GET(self):
        path = urllib.parse.unquote(self.path.split("?")[0])

        # style.css is an app asset that lives next to gui.py — served from
        # the app's own folder, NOT from the user's shared_root.
        if path == "/style.css":
            asset_path = os.path.join(APP_DIR, "style.css")
            if not os.path.isfile(asset_path):
                self.send_error(404, "Not Found")
                return
            self._serve_static_asset(asset_path)
            return

        if os.path.isfile(self.shared_root):
            self._serve_file(self.shared_root)
            return

        fs_path = os.path.normpath(os.path.join(self.shared_root, path.lstrip("/")))

        if not fs_path.startswith(os.path.abspath(self.shared_root)):
            self.send_error(403, "Forbidden")
            return

        if os.path.isfile(fs_path):
            self._serve_file(fs_path)
        elif os.path.isdir(fs_path):
            self._serve_directory(fs_path, path)
        else:
            self.send_error(404, "Not Found")

    def _serve_static_asset(self, fs_path):
        """Serves an app asset (e.g. static/style.css) inline — no
        Content-Disposition: attachment, so the browser applies it (as CSS)
        instead of trying to download it."""
        try:
            file_size = os.path.getsize(fs_path)
            self.send_response(200)
            self.send_header("Content-Length", str(file_size))
            mime, _ = mimetypes.guess_type(fs_path)
            self.send_header("Content-Type", mime or "application/octet-stream")
            self.end_headers()
            with open(fs_path, "rb") as f:
                while chunk := f.read(65536):
                    self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _serve_file(self, fs_path):
        try:
            file_size = os.path.getsize(fs_path)
            filename = os.path.basename(fs_path)
            self.send_response(200)
            self.send_header("Content-Length", str(file_size))
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            mime, _ = mimetypes.guess_type(fs_path)
            self.send_header("Content-Type", mime or "application/octet-stream")
            self.end_headers()
            with open(fs_path, "rb") as f:
                while chunk := f.read(65536):
                    self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            self.send_error(500, str(e))

    def _serve_directory(self, fs_path, url_path):
        try:
            entries = list(os.scandir(fs_path))
        except PermissionError:
            self.send_error(403, "Permission denied")
            return

        dirs  = sorted([e for e in entries if not e.name.startswith(".") and e.is_dir(follow_symlinks=False)],  key=lambda e: e.name.lower())
        files = sorted([e for e in entries if not e.name.startswith(".") and e.is_file(follow_symlinks=False)], key=lambda e: e.name.lower())

        rows_html = ""
        if url_path.strip("/"):
            parent = "/" + "/".join(url_path.strip("/").split("/")[:-1])
            rows_html += f'<a class="file-item is-dir" href="{parent or "/"}"><div class="file-name"><span>⬆️</span><span class="file-label">.. (Parent Folder)</span></div><div class="file-size">—</div><div class="download-btn"></div></a>'

        for e in dirs:
            eu = url_path.rstrip("/") + "/" + urllib.parse.quote(e.name)
            rows_html += f'<a class="file-item is-dir" href="{eu}/"><div class="file-name"><span>📂</span><span class="file-label">{html.escape(e.name)}</span></div><div class="file-size">—</div><div class="download-btn">Open →</div></a>'

        for e in files:
            try:   size = e.stat().st_size
            except: size = 0
            eu   = url_path.rstrip("/") + "/" + urllib.parse.quote(e.name)
            icon = get_file_icon(e.name)
            rows_html += f'<a class="file-item" href="{eu}" download><div class="file-name"><span>{icon}</span><span class="file-label">{html.escape(e.name)}</span></div><div class="file-size">{human_size(size)}</div><div class="download-btn">⬇ Download</div></a>'

        if not dirs and not files:
            rows_html = '<div style="text-align:center;padding:3rem;color:#9CA3AF;">📭 Folder is empty.</div>'

        breadcrumb_html = '<a href="/">🏠 Home</a>'
        parts = [p for p in url_path.strip("/").split("/") if p]
        for i, part in enumerate(parts):
            href = "/" + "/".join(parts[:i+1])
            breadcrumb_html += f' / <a href="{href}">{html.escape(urllib.parse.unquote(part))}</a>'

        ip   = get_local_ip()
        port = self.server.server_address[1]
        page = HTML_TEMPLATE.format(
            current_path=url_path or "/",
            server_address=f"http://{ip}:{port}",
            breadcrumb_html=breadcrumb_html,
            file_rows=rows_html,
        ).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(page)))
        self.end_headers()
        self.wfile.write(page)

    def log_message(self, format, *args):
        pass


# ─── Modern CustomTkinter GUI ───────────────────────────────────────────────

ctk.set_appearance_mode("dark")

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Local Network QR File Sharer")
        self.geometry("640x660+200+30")
        self.resizable(False, False)
        self.configure(fg_color="#0B0E14")

        self._server     = None
        self._srv_thread = None
        self.is_running  = False
        self.current_url = ""
        self.selected_path = os.path.abspath(".")
        self.PORT = 8000

        self._build_ui()

    def _build_ui(self):

        # ── Header ──────────────────────────────────────────────
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", padx=24, pady=(24, 14))
        title_box = ctk.CTkFrame(hdr, fg_color="transparent")
        title_box.pack(side="left")

        ctk.CTkLabel(
            title_box,
            text="📡  QRShare",
            font=ctk.CTkFont(family= "Calibri", size=26, weight="bold"),
            text_color="#F3F4F6"
        ).pack(anchor="w")

        ctk.CTkLabel(
            title_box,
            text="Instant LAN File Transfer Hub",
            font=ctk.CTkFont(family= "Consolas", size=14),
            text_color="#6B7280"
        ).pack(anchor="w")

        self.badge = ctk.CTkLabel(
            hdr,
            text="● OFFLINE",
            font=ctk.CTkFont(family= "Consolas", size=12, weight="bold"),
            text_color="#EF4444",
            fg_color="#2A1215",
            corner_radius=20,
            padx=12, pady=5,
        )
        self.badge.pack(side="right")

        # ── Path Card ───────────────────────────────────────────
        card = ctk.CTkFrame(self, fg_color="#151C2C", corner_radius=16, border_width=1, border_color="#26334D")
        card.pack(fill="x", padx=24, pady=(0, 16))

        path_hdr = ctk.CTkFrame(card, fg_color="transparent")
        path_hdr.pack(fill="x", padx=16, pady=(14, 6))

        ctk.CTkLabel(
            path_hdr,
            text="SELECTED RESOURCE",
            font=ctk.CTkFont(family= "Consolas", size=14, weight="bold"),
            text_color="#00F2FE"
        ).pack(side="left")

        self.type_lbl = ctk.CTkLabel(
            path_hdr,
            text="FOLDER",
            font=ctk.CTkFont(family= "Consolas", size=12, weight="bold"),
            text_color="#9CA3AF"
        )
        self.type_lbl.pack(side="right")

        self.path_entry = ctk.CTkEntry(
            card,
            font=ctk.CTkFont(family= "Consolas",size=12),
            fg_color="#0B0E14",
            border_color="#26334D",
            text_color="#E5E7EB",
            height=38,
            corner_radius=10
        )
        self.path_entry.insert(0, self.selected_path)
        self.path_entry.pack(fill="x", padx=16, pady=(0, 12))

        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(0, 14))

        ctk.CTkButton(
            btn_row, text="📂  Browse Folder", width=140, height=34,
            fg_color="#1E293B", hover_color="#334155", text_color="#F3F4F6",
            font=ctk.CTkFont(family= "Consolas",size=14, weight="bold"), corner_radius=8,
            command=self._pick_folder,
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            btn_row, text="📄  Browse File", width=140, height=34,
            fg_color="#1E293B", hover_color="#334155", text_color="#F3F4F6",
            font=ctk.CTkFont(family= "Consolas", size=14, weight="bold"), corner_radius=8,
            command=self._pick_file,
        ).pack(side="left")

        # ── QR Code Display Card ────────────────────────────────
        self.qr_card = ctk.CTkFrame(self, fg_color="#151C2C", corner_radius=16, border_width=1, border_color="#26334D")
        self.qr_card.pack(fill="both", expand=True, padx=24, pady=(0, 16))

        # Placeholder when offline
        self.qr_placeholder_frame = ctk.CTkFrame(self.qr_card, fg_color="transparent")
        self.qr_placeholder_frame.pack(expand=True)

        ctk.CTkLabel(
            self.qr_placeholder_frame,
            text="📲",
            font=ctk.CTkFont(family= "Consolas", size=50)
        ).pack(pady=(0, 10))

        ctk.CTkLabel(
            self.qr_placeholder_frame,
            text="Ready to Broadcast",
            font=ctk.CTkFont(family= "Calibri", size=17, weight="bold"),
            text_color="#E5E7EB"
        ).pack()

        ctk.CTkLabel(
            self.qr_placeholder_frame,
            text="Click 'Start Server' below to generate your QR Code\nand share with devices on your Wi-Fi.",
            font=ctk.CTkFont(family= "Calibri", size=12),
            text_color="#6B7280",
            justify="center"
        ).pack(pady=(6, 0))

        # QR Image container (Hidden initially)
        self.qr_content_frame = ctk.CTkFrame(self.qr_card, fg_color="transparent")

        self.qr_img_label = ctk.CTkLabel(self.qr_content_frame, text="")
        self.qr_img_label.pack(pady=(16, 10))

        # Server Address Box
        self.url_box = ctk.CTkFrame(self.qr_content_frame, fg_color="#0B0E14", corner_radius=10, border_width=1, border_color="#26334D")
        self.url_box.pack(fill="x", padx=20, pady=(0, 16))

        self.url_lbl = ctk.CTkLabel(
            self.url_box,
            text="",
            font=ctk.CTkFont(size=13, weight="bold", family="Consolas"),
            text_color="#10B981",
        )
        self.url_lbl.pack(side="left", padx=14, pady=8)

        ctk.CTkButton(
            self.url_box,
            text="📋 Copy IP",
            width=80, height=28,
            fg_color="#10B981", hover_color="#059669", text_color="#0B0E14",
            font=ctk.CTkFont(family= "Consolas",size=11, weight="bold"), corner_radius=6,
            command=self._copy_link,
        ).pack(side="right", padx=8, pady=8)

        # ── Toggle Action Button ────────────────────────────────
        self.toggle_btn = ctk.CTkButton(
            self,
            text="🚀  Start Server",
            font=ctk.CTkFont(family= "Segoe UI", size=16, weight="bold"),
            height=50,
            corner_radius=12,
            fg_color="#10B981", hover_color="#059669", text_color="#0B0E14",
            command=self._toggle,
        )
        self.toggle_btn.pack(fill="x", padx=24, pady=(0, 24))

    # ── Actions ────────────────────────────────────────────────────────────
    def _pick_folder(self):
        p = filedialog.askdirectory()
        if p:
            self._set_path(os.path.abspath(p), "FOLDER")

    def _pick_file(self):
        p = filedialog.askopenfilename()
        if p:
            self._set_path(os.path.abspath(p), "FILE")

    def _set_path(self, path: str, path_type: str = "RESOURCE"):
        self.selected_path = path
        self.type_lbl.configure(text=path_type)
        self.path_entry.delete(0, "end")
        self.path_entry.insert(0, path)

    def _toggle(self):
        if self.is_running:
            self._stop()
        else:
            self._start()

    def _start(self):
        try:
            path = self.path_entry.get().strip().strip('"').strip("'")
            if not path or not os.path.exists(path):
                messagebox.showerror("Path Error", f"The specified path does not exist:\n{path}")
                return

            self.selected_path = os.path.abspath(path)
            FileShareHandler.shared_root = self.selected_path

            socketserver.TCPServer.allow_reuse_address = True
            self._server = socketserver.TCPServer(("", self.PORT), FileShareHandler)

            self._srv_thread = threading.Thread(target=self._server.serve_forever, daemon=True)
            self._srv_thread.start()
            self.is_running = True

            # Build QR image
            ip = get_local_ip()
            self.current_url = f"http://{ip}:{self.PORT}"

            qr = qrcode.QRCode(box_size=7, border=2, error_correction=qrcode.constants.ERROR_CORRECT_L)
            qr.add_data(self.current_url)
            qr.make(fit=True)
            
            # Convert to PIL Image cleanly
            pil_img = qr.make_image(fill_color="#00F2FE", back_color="#0B0E14").get_image()

            ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(210, 210))

            self.qr_placeholder_frame.pack_forget()
            self.qr_img_label.configure(image=ctk_img)
            self.qr_content_frame.pack(fill="both", expand=True)

            self.url_lbl.configure(text=self.current_url)

            # Update status badge & button
            self.badge.configure(text="● ONLINE", text_color="#10B981", fg_color="#122A22")
            self.toggle_btn.configure(text="⏹  Stop Server", fg_color="#EF4444", hover_color="#DC2626", text_color="#FFFFFF")

        except Exception as e:
            import traceback
            messagebox.showerror("Server Error", traceback.format_exc())

    def _stop(self):
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

        self.is_running  = False
        self.current_url = ""

        self.qr_content_frame.pack_forget()
        self.qr_placeholder_frame.pack(expand=True)

        self.badge.configure(text="● OFFLINE", text_color="#EF4444", fg_color="#2A1215")
        self.toggle_btn.configure(text="🚀  Start Server", fg_color="#10B981", hover_color="#059669", text_color="#0B0E14")

    def _copy_link(self):
        if self.current_url:
            self.clipboard_clear()
            self.clipboard_append(self.current_url)
            messagebox.showinfo("Copied!", f"Server Address Copied:\n{self.current_url}")


if __name__ == "__main__":
    app = App()
    app.mainloop()
