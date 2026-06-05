#!/usr/bin/env python3
"""
DeepSeek Balance Widget — 桌面余额挂件
实时显示 DeepSeek API 账户余额，自动刷新，置顶显示
零依赖，仅需 Python 3 标准库

快捷键: Ctrl+Alt+D 一键显示/隐藏窗口
"""

import tkinter as tk
import json
import os
import sys
import threading
import tempfile
import atexit
import urllib.request
import urllib.error
import platform
from datetime import datetime
from pathlib import Path

# ─── 配置 ───────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent.resolve()
CONFIG_DIR = SCRIPT_DIR / ".ds_widget"
CONFIG_DIR.mkdir(exist_ok=True)
CONFIG_FILE = CONFIG_DIR / "config.json"
LOCK_FILE = Path(tempfile.gettempdir()) / ".ds_widget.lock"
API_URL = "https://api.deepseek.com/user/balance"
REFRESH_INTERVAL = 30
HOTKEY_ID = 0xC0DE  # 全局热键 ID

# ─── 深色主题 ───────────────────────────────────────────────
C_BG       = "#0d1117"
C_CARD     = "#161b22"
C_ACCENT   = "#00d4aa"
C_WARN     = "#f0883e"
C_ERROR    = "#f85149"
C_TEXT     = "#e6edf3"
C_MUTED    = "#8b949e"
C_TITLE_BG = "#0d1117"


# ═══════════════════════════════════════════════════════════
#  单例锁
# ═══════════════════════════════════════════════════════════

def try_lock() -> bool:
    try:
        if LOCK_FILE.exists():
            pid_s = LOCK_FILE.read_text().strip()
            if pid_s.isdigit() and _pid_alive(int(pid_s)):
                _signal_show()
                return False
        LOCK_FILE.write_text(str(os.getpid()), encoding="utf-8")
        return True
    except Exception:
        return True


def _pid_alive(pid: int) -> bool:
    if os.name == "nt":
        try:
            import ctypes
            h = ctypes.windll.kernel32.OpenProcess(0x0400, False, pid)
            if h:
                ctypes.windll.kernel32.CloseHandle(h)
                return True
        except Exception:
            pass
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _signal_show():
    try:
        (CONFIG_DIR / "show.signal").write_text("1", encoding="utf-8")
    except Exception:
        pass


def release_lock():
    try:
        if LOCK_FILE.exists() and LOCK_FILE.read_text().strip() == str(os.getpid()):
            LOCK_FILE.unlink(missing_ok=True)
    except Exception:
        pass


atexit.register(release_lock)


# ═══════════════════════════════════════════════════════════
#  API
# ═══════════════════════════════════════════════════════════

def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"api_key": ""}


def save_config(cfg: dict):
    try:
        CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def fetch_balance(api_key: str):
    if not api_key:
        return None, "请先设置 API Key"

    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    try:
        req = urllib.request.Request(API_URL, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8")), None
    except urllib.error.HTTPError as e:
        if e.code == 401:  return None, "API Key 无效"
        if e.code == 429:  return None, "请求过于频繁"
        return None, f"HTTP {e.code}"
    except urllib.error.URLError:  return None, "网络不可达"
    except TimeoutError:           return None, "连接超时"
    except Exception as e:         return None, str(e)


def parse_balance(data: dict) -> tuple:
    if not data:               return 0.0, True, "无数据"
    is_avail = bool(data.get("is_available", True))
    infos = data.get("balance_infos")

    if infos and isinstance(infos, list):
        total = 0.0; parts = []
        for i in infos:
            tb = float(i.get("total_balance", 0)); total += tb
            t = float(i.get("topped_up_balance", 0))
            g = float(i.get("granted_balance", 0))
            if t or g: parts.append(f"充值 {t:.2f} | 赠送 {g:.2f}")
        return total, is_avail, "  ".join(parts)

    if "balance" in data and data["balance"] is not None:
        return float(data["balance"]), is_avail, ""

    for k in ("available_balance", "remaining", "credit"):
        if k in data:
            try: return float(data[k]), True, ""
            except: pass
    return 0.0, True, "未知响应格式"


# ═══════════════════════════════════════════════════════════
#  全局热键（Windows）
# ═══════════════════════════════════════════════════════════

def register_hotkey(hwnd):
    """注册 Ctrl+Alt+D 全局热键"""
    if platform.system() != "Windows":
        return False
    try:
        import ctypes
        user32 = ctypes.windll.user32
        MOD_ALT = 0x0001; MOD_CONTROL = 0x0002; MOD_NOREPEAT = 0x4000
        # 先取消注册旧的（如果有）
        user32.UnregisterHotKey(None, HOTKEY_ID)
        result = user32.RegisterHotKey(None, HOTKEY_ID,
                                        MOD_CONTROL | MOD_ALT | MOD_NOREPEAT,
                                        ord('D'))
        return result != 0
    except Exception:
        return False


def unregister_hotkey():
    if platform.system() != "Windows":
        return
    try:
        import ctypes
        ctypes.windll.user32.UnregisterHotKey(None, HOTKEY_ID)
    except Exception:
        pass


atexit.register(unregister_hotkey)


# ═══════════════════════════════════════════════════════════
#  设置对话框
# ═══════════════════════════════════════════════════════════

class SettingsDialog:
    def __init__(self, parent, current_key, callback):
        self.callback = callback
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("设置")
        self.dialog.configure(bg=C_BG)
        self.dialog.geometry("420x200")
        self.dialog.resizable(False, False)
        self.dialog.attributes("-topmost", True)
        self.dialog.transient(parent)
        self.dialog.grab_set()

        self.dialog.update_idletasks()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        px, py = parent.winfo_x(), parent.winfo_y()
        self.dialog.geometry(f"+{px+(pw-420)//2}+{py+(ph-200)//2}")

        tk.Label(self.dialog, text="DeepSeek API 设置",
                 bg=C_BG, fg=C_TEXT, font=("Microsoft YaHei", 12, "bold")).pack(pady=(16, 8))

        frame = tk.Frame(self.dialog, bg=C_BG)
        frame.pack(pady=4)
        tk.Label(frame, text="API Key:", bg=C_BG, fg=C_TEXT,
                 font=("Microsoft YaHei", 10)).pack(side="left")
        self.entry = tk.Entry(frame, width=36, show="●",
                              bg=C_CARD, fg=C_TEXT, insertbackground=C_TEXT,
                              font=("Consolas", 10), relief="flat", bd=8)
        self.entry.insert(0, current_key)
        self.entry.pack(side="left", padx=(8, 4))
        self.show_btn = tk.Button(frame, text="👁", command=self._toggle_show,
                                  bg=C_CARD, fg=C_MUTED, bd=0, cursor="hand2")
        self.show_btn.pack(side="left")

        tk.Label(self.dialog, text="在 platform.deepseek.com/api_keys 获取",
                 bg=C_BG, fg=C_MUTED, font=("Microsoft YaHei", 8)).pack(pady=(0, 8))
        btn_frame = tk.Frame(self.dialog, bg=C_BG)
        btn_frame.pack(pady=6)
        for t, bg, fg, cmd in [
            ("保存", C_ACCENT, "#0d1117", self._save),
            ("取消", "#21262d", C_TEXT, self.dialog.destroy),
        ]:
            tk.Button(btn_frame, text=t, bg=bg, fg=fg, bd=0,
                      padx=20, pady=4, cursor="hand2",
                      font=("Microsoft YaHei", 9), command=cmd).pack(side="left", padx=6)

    def _toggle_show(self):
        if self.entry.cget("show") == "●":
            self.entry.config(show=""); self.show_btn.config(text="🙈")
        else:
            self.entry.config(show="●"); self.show_btn.config(text="👁")

    def _save(self):
        key = self.entry.get().strip()
        if key: self.callback(key)
        self.dialog.destroy()


# ═══════════════════════════════════════════════════════════
#  主挂件
# ═══════════════════════════════════════════════════════════

class BalanceWidget:
    def __init__(self):
        self.config = load_config()
        self.error = None
        self._hotkey_ok = register_hotkey(None)

        self.root = tk.Tk()
        self.root.title("DeepSeek Balance Widget")
        self._setup_window()
        self._setup_ui()
        self._bind_events()
        self._poll_signal()
        self._poll_hotkey()
        self.root.after(500, self.refresh_balance)
        self._auto_refresh()
        self.root.mainloop()

    def _setup_window(self):
        self.root.overrideredirect(True)
        self.root.geometry("240x190")
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.94)
        self.root.configure(bg=C_BG)
        sw = self.root.winfo_screenwidth()
        self.root.geometry(f"+{sw-240-30}+90")
        # 不在任务栏显示
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
            ctypes.windll.user32.SetWindowLongW(hwnd, -20, style | 0x00000080)
        except Exception:
            pass

    def _setup_ui(self):
        # 标题栏
        self.title_bar = tk.Frame(self.root, bg=C_TITLE_BG, height=28)
        self.title_bar.pack(fill="x")
        self.title_bar.pack_propagate(False)
        tk.Label(self.title_bar, text="DeepSeek 余额", bg=C_TITLE_BG, fg=C_MUTED,
                 font=("Microsoft YaHei", 9)).pack(side="left", padx=10, pady=4)
        tk.Button(self.title_bar, text="—", bg=C_TITLE_BG, fg=C_MUTED, bd=0, cursor="hand2",
                  font=("Segoe UI", 10), command=self.hide_widget).pack(side="right", padx=2)
        tk.Button(self.title_bar, text="✕", bg=C_TITLE_BG, fg=C_MUTED, bd=0, cursor="hand2",
                  font=("Segoe UI", 10), command=self.root.quit).pack(side="right", padx=(2, 6))

        # 内容
        self.content = tk.Frame(self.root, bg=C_BG)
        self.content.pack(fill="both", expand=True)
        self.balance_var = tk.StringVar(value="---")
        self.balance_label = tk.Label(self.content, textvariable=self.balance_var,
                                      bg=C_BG, fg=C_ACCENT, font=("Segoe UI", 38, "bold"))
        self.balance_label.pack(pady=(16, 0))
        self.sub_var = tk.StringVar(value="CNY  ·  等待刷新")
        tk.Label(self.content, textvariable=self.sub_var, bg=C_BG, fg=C_MUTED,
                 font=("Microsoft YaHei", 9)).pack()
        self.status_var = tk.StringVar(value="")
        tk.Label(self.content, textvariable=self.status_var, bg=C_BG, fg=C_MUTED,
                 font=("Consolas", 8)).pack(pady=(4, 0))

        # 底部
        bottom = tk.Frame(self.root, bg=C_BG)
        bottom.pack(fill="x", side="bottom", pady=(0, 6))
        tk.Button(bottom, text="⟳ 刷新", bg=C_BG, fg=C_MUTED, bd=0, cursor="hand2",
                  font=("Microsoft YaHei", 8), command=self.refresh_balance).pack(side="left", padx=8)
        tk.Button(bottom, text="⚙ 设置", bg=C_BG, fg=C_MUTED, bd=0, cursor="hand2",
                  font=("Microsoft YaHei", 8), command=self.open_settings).pack(side="right", padx=8)

        if not self.config.get("api_key"):
            self.status_var.set("右键 → 设置 → 输入 API Key")

    def _bind_events(self):
        drag = {"x": 0, "y": 0}

        def press(e):
            drag["x"], drag["y"] = e.x, e.y

        def move(e):
            self.root.geometry(f"+{self.root.winfo_x()+e.x-drag['x']}+{self.root.winfo_y()+e.y-drag['y']}")

        for w in (self.title_bar, self.content, self.balance_label):
            w.bind("<Button-1>", press)
            w.bind("<B1-Motion>", move)

        self.title_bar.bind("<Double-Button-1>", lambda e: self.open_settings())
        self.root.bind("<Escape>", lambda e: self.root.quit())

        menu = tk.Menu(self.root, tearoff=0, bg=C_CARD, fg=C_TEXT,
                       activebackground=C_ACCENT, activeforeground=C_BG,
                       font=("Microsoft YaHei", 9))
        menu.add_command(label="⟳ 刷新", command=self.refresh_balance)
        menu.add_command(label="⚙ 设置", command=self.open_settings)
        menu.add_separator()
        self._top_var = tk.BooleanVar(value=True)
        menu.add_checkbutton(label="置顶显示", variable=self._top_var,
                             command=lambda: self.root.attributes("-topmost", self._top_var.get()))
        menu.add_separator()

        if self._hotkey_ok:
            menu.add_command(label="隐藏（Ctrl+Alt+D 呼出）", command=self.hide_widget)
        else:
            menu.add_command(label="隐藏", command=self.hide_widget)
        menu.add_command(label="✕ 退出", command=self.root.quit)

        for w in (self.root, self.content, self.balance_label):
            w.bind("<Button-3>", lambda e: menu.tk_popup(e.x_root, e.y_root))

    # ── 显示 / 隐藏 ──
    def hide_widget(self):
        self.root.withdraw()

    def show_widget(self):
        self.root.deiconify()
        self.root.lift()
        self.refresh_balance()

    def toggle_visibility(self):
        try:
            if self.root.state() == "withdrawn" or not self.root.winfo_ismapped():
                self.show_widget()
            else:
                self.hide_widget()
        except Exception:
            self.show_widget()

    def _poll_signal(self):
        sig = CONFIG_DIR / "show.signal"
        if sig.exists():
            try:
                sig.unlink(missing_ok=True)
                self.show_widget()
            except Exception:
                pass
        self.root.after(2000, self._poll_signal)

    def _poll_hotkey(self):
        """每 200ms 检查全局热键消息"""
        if self._hotkey_ok and platform.system() == "Windows":
            try:
                import ctypes
                from ctypes import wintypes
                user32 = ctypes.windll.user32
                WM_HOTKEY = 0x0312
                msg = wintypes.MSG()
                while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                    if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                        self.toggle_visibility()
            except Exception:
                pass
        self.root.after(200, self._poll_hotkey)

    # ── 数据 ──
    def refresh_balance(self):
        api_key = self.config.get("api_key", "")
        if not api_key:
            self.update_display(None, "请设置 API Key")
            return

        def fetch():
            data, err = fetch_balance(api_key)
            self.root.after(0, self.update_display, data, err)

        threading.Thread(target=fetch, daemon=True).start()

    def update_display(self, data, error):
        if error:
            self.balance_var.set("--.--"); self.balance_label.configure(fg=C_ERROR)
            self.sub_var.set("CNY"); self.status_var.set(f"⚠ {error}")
            self._update_time(); return

        balance, available, detail = parse_balance(data)
        if balance < 0:         color, status = C_ERROR, "数据异常"
        elif balance < 1:       color, status = C_WARN, "余额不足"
        elif not available:     color, status = C_ERROR, "账户不可用"
        else:                   color, status = C_ACCENT, "正常"

        self.balance_var.set(f"{balance:.2f}")
        self.balance_label.configure(fg=color)
        self.sub_var.set(f"CNY  ·  {status}")
        self.status_var.set(detail if detail else "")
        self._update_time()

    def _update_time(self):
        self.status_var.set(self.status_var.get().rstrip() + f"  更新 {datetime.now():%H:%M:%S}")

    def _auto_refresh(self):
        self.refresh_balance()
        self.root.after(REFRESH_INTERVAL * 1000, self._auto_refresh)

    def open_settings(self):
        SettingsDialog(self.root, self.config.get("api_key", ""), self._on_save_key)

    def _on_save_key(self, key):
        self.config["api_key"] = key
        save_config(self.config)
        self.refresh_balance()


# ═══════════════════════════════════════════════════════════
#  入口
# ═══════════════════════════════════════════════════════════

def main():
    if not try_lock():
        sys.exit(0)
    BalanceWidget()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        log = SCRIPT_DIR / "ds_widget_error.log"
        try:
            log.write_text(f"{datetime.now()}\n{e}\n{traceback.format_exc()}", encoding="utf-8")
        except Exception:
            pass
        print(f"[ds_widget] 启动失败: {e}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
