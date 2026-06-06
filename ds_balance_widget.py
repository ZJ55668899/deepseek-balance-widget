#!/usr/bin/env python3
"""
DeepSeek Balance Widget — 桌面余额挂件
实时显示 DeepSeek API 余额，统计消耗进度，估算剩余 Token
零依赖，仅需 Python 3 标准库
快捷键: Ctrl+Alt+D 显示/隐藏
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
STATE_FILE = CONFIG_DIR / "state.json"
LOCK_FILE = Path(tempfile.gettempdir()) / ".ds_widget.lock"
API_URL = "https://api.deepseek.com/user/balance"
REFRESH_INTERVAL = 30
HOTKEY_ID = 0xC0DE
TOKEN_PRICE = 0.000003  # ¥/token 约 ¥3/1M tokens

# ─── 色板 ───────────────────────────────────────────────────
C_BG       = "#070b14"
C_CARD     = "#0f1729"
C_CYAN     = "#00d4ff"
C_PURPLE   = "#7c3aed"
C_WARN     = "#f59e0b"
C_ERROR    = "#ef4444"
C_TEXT     = "#e2e8f0"
C_MUTED    = "#475569"
C_DIM      = "#1e293b"
C_GREEN    = "#22c55e"
W, H       = 280, 210


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


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_state(state: dict):
    try:
        STATE_FILE.write_text(json.dumps(state), encoding="utf-8")
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


def parse_balance(data: dict) -> dict:
    r = {"balance": 0, "topped": 0, "granted": 0, "is_available": True}
    if not data:
        return r
    r["is_available"] = bool(data.get("is_available", True))
    infos = data.get("balance_infos")
    if infos and isinstance(infos, list):
        for i in infos:
            r["balance"] += float(i.get("total_balance", 0))
            r["topped"] += float(i.get("topped_up_balance", 0))
            r["granted"] += float(i.get("granted_balance", 0))
    elif "balance" in data and data["balance"] is not None:
        r["balance"] = float(data["balance"])
        r["topped"] = r["balance"]
    return r


# ═══════════════════════════════════════════════════════════
#  热键
# ═══════════════════════════════════════════════════════════

def _register_hotkey(hwnd) -> bool:
    if platform.system() != "Windows":
        return False
    try:
        import ctypes
        u = ctypes.windll.user32
        u.UnregisterHotKey(hwnd, HOTKEY_ID)
        return bool(u.RegisterHotKey(hwnd, HOTKEY_ID, 0x0002 | 0x0001 | 0x4000, ord('D')))
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

        tk.Label(self.dialog, text="DEEPSEEK API SETUP",
                 bg=C_BG, fg=C_CYAN, font=("Consolas", 12, "bold")).pack(pady=(16, 8))

        frame = tk.Frame(self.dialog, bg=C_BG)
        frame.pack(pady=4)
        tk.Label(frame, text="API Key:", bg=C_BG, fg=C_TEXT,
                 font=("Consolas", 10)).pack(side="left")
        self.entry = tk.Entry(frame, width=36, show="●",
                              bg=C_CARD, fg=C_TEXT, insertbackground=C_CYAN,
                              font=("Consolas", 10), relief="flat", bd=8)
        self.entry.insert(0, current_key)
        self.entry.pack(side="left", padx=(8, 4))
        self.show_btn = tk.Button(frame, text="SHOW", command=self._toggle_show,
                                  bg=C_CARD, fg=C_MUTED, bd=0, cursor="hand2",
                                  font=("Consolas", 8))
        self.show_btn.pack(side="left")

        tk.Label(self.dialog, text="platform.deepseek.com/api_keys",
                 bg=C_BG, fg=C_MUTED, font=("Consolas", 8)).pack(pady=(0, 8))
        btn_frame = tk.Frame(self.dialog, bg=C_BG)
        btn_frame.pack(pady=6)
        for t, bg, fg, cmd in [
            ("[SAVE]", C_CYAN, "#0d1117", self._save),
            ("[CANCEL]", C_DIM, C_TEXT, self.dialog.destroy),
        ]:
            tk.Button(btn_frame, text=t, bg=bg, fg=fg, bd=0,
                      padx=20, pady=4, cursor="hand2",
                      font=("Consolas", 9), command=cmd).pack(side="left", padx=6)

    def _toggle_show(self):
        if self.entry.cget("show") == "●":
            self.entry.config(show=""); self.show_btn.config(text="HIDE")
        else:
            self.entry.config(show="●"); self.show_btn.config(text="SHOW")

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
        self.state = load_state()
        self.initial_balance = self.state.get("initial_balance")
        self.balance_data = None

        self.root = tk.Tk()
        self.root.title("DeepSeek Balance Widget")
        self._setup_window()
        self._setup_ui()
        self._hotkey_ok = _register_hotkey(self._get_hwnd())
        self._bind_events()
        self._poll_signal()
        self._poll_hotkey()
        self.root.after(500, self.refresh_balance)
        self._auto_refresh()
        self.root.mainloop()

    # ── 窗口 ──
    def _get_hwnd(self):
        try:
            import ctypes
            return ctypes.windll.user32.GetParent(self.root.winfo_id())
        except Exception:
            return None

    def _setup_window(self):
        self.root.overrideredirect(True)
        self.root.geometry(f"{W}x{H}")
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.95)
        self.root.configure(bg=C_BG)
        sw = self.root.winfo_screenwidth()
        self.root.geometry(f"+{sw-W-30}+90")
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
            ctypes.windll.user32.SetWindowLongW(hwnd, -20, style | 0x00000080)
        except Exception:
            pass

    # ── UI ──
    def _setup_ui(self):
        # 标题栏
        self.title_bar = tk.Frame(self.root, bg=C_CARD, height=32)
        self.title_bar.pack(fill="x")
        self.title_bar.pack_propagate(False)
        tk.Label(self.title_bar, text="⚡ DeepSeek", bg=C_CARD, fg=C_CYAN,
                 font=("Consolas", 10, "bold")).pack(side="left", padx=12, pady=4)
        tk.Button(self.title_bar, text="—", bg=C_CARD, fg=C_MUTED, bd=0, cursor="hand2",
                  font=("Consolas", 10), command=self.hide_widget).pack(side="right", padx=2)
        tk.Button(self.title_bar, text="✕", bg=C_CARD, fg=C_MUTED, bd=0, cursor="hand2",
                  font=("Consolas", 10), command=self.root.quit).pack(side="right", padx=(2, 8))

        # 内容
        self.content = tk.Frame(self.root, bg=C_BG)
        self.content.pack(fill="both", expand=True, padx=20, pady=(4, 0))

        # 余额
        self.balance_var = tk.StringVar(value="--.--")
        self.balance_label = tk.Label(self.content, textvariable=self.balance_var,
                                      bg=C_BG, fg=C_CYAN, font=("Consolas", 38, "bold"))
        self.balance_label.pack(pady=(4, 0))

        self.sub_var = tk.StringVar(value="CNY  ·  余额")
        tk.Label(self.content, textvariable=self.sub_var, bg=C_BG, fg=C_MUTED,
                 font=("Consolas", 9)).pack()

        # ── 进度条（充值占比） ──
        self.prog_canvas = tk.Canvas(self.content, bg=C_DIM, height=22, highlightthickness=0)
        self.prog_canvas.pack(fill="x", pady=(8, 0))

        # 消耗 / 充值 / Token
        self.consume_var = tk.StringVar(value="消耗 --")
        self.topped_var = tk.StringVar(value="充值 --.--")
        self.token_var = tk.StringVar(value="≈ -- M Tokens")

        row1 = tk.Frame(self.content, bg=C_BG)
        row1.pack(fill="x", pady=(1, 0))
        tk.Label(row1, textvariable=self.consume_var,
                 bg=C_BG, fg=C_WARN, font=("Consolas", 8, "bold")).pack(side="left")
        tk.Label(row1, text="|", bg=C_BG, fg=C_DIM,
                 font=("Consolas", 8)).pack(side="left", padx=4)
        tk.Label(row1, textvariable=self.topped_var,
                 bg=C_BG, fg=C_CYAN, font=("Consolas", 8)).pack(side="left")
        tk.Label(row1, textvariable=self.token_var,
                 bg=C_BG, fg=C_GREEN, font=("Consolas", 8)).pack(side="right")

        # 底部栏
        self.status_var = tk.StringVar(value="等待刷新")
        bottom = tk.Frame(self.root, bg=C_BG)
        bottom.pack(fill="x", side="bottom", pady=(0, 6))
        tk.Label(bottom, textvariable=self.status_var, bg=C_BG, fg=C_MUTED,
                 font=("Consolas", 7)).pack(side="left", padx=12)
        tk.Button(bottom, text="[REFRESH]", bg=C_BG, fg=C_MUTED, bd=0, cursor="hand2",
                  font=("Consolas", 8), command=self.refresh_balance).pack(side="right", padx=6)
        tk.Button(bottom, text="[SETUP]", bg=C_BG, fg=C_MUTED, bd=0, cursor="hand2",
                  font=("Consolas", 8), command=self.open_settings).pack(side="right", padx=(0, 12))

        if not self.config.get("api_key"):
            self.status_var.set("Right-click > SETUP > enter API Key")

        self.root.update_idletasks()
        self._draw_progress(0)

    def _draw_progress(self, ratio: float):
        """充值占比进度条"""
        cw = self.prog_canvas.winfo_width() or (W - 40)
        ch = 22
        self.prog_canvas.delete("all")
        r = 4
        self.prog_canvas.create_rounded_rect(0, 0, cw, ch, r, fill=C_DIM, outline="")
        fw = int(cw * min(1, ratio))
        if fw > 0:
            self.prog_canvas.create_rounded_rect(0, 0, fw, ch, r, fill=C_CYAN, outline="")
        self.prog_canvas.create_text(cw // 2, ch // 2,
                                      text=f"{ratio*100:.1f}%" if ratio > 0 else "0.0%",
                                      fill=C_TEXT, font=("Consolas", 10, "bold"), anchor="center")

    # ── 交互 ──
    def _bind_events(self):
        drag = {"x": 0, "y": 0}

        def press(e):
            drag["x"], drag["y"] = e.x, e.y

        def move(e):
            self.root.geometry(f"+{self.root.winfo_x()+e.x-drag['x']}+{self.root.winfo_y()+e.y-drag['y']}")

        for w in (self.title_bar, self.content):
            w.bind("<Button-1>", press)
            w.bind("<B1-Motion>", move)

        self.title_bar.bind("<Double-Button-1>", lambda e: self.open_settings())
        self.root.bind("<Escape>", lambda e: self.root.quit())

        menu = tk.Menu(self.root, tearoff=0, bg=C_CARD, fg=C_TEXT,
                       activebackground=C_CYAN, activeforeground=C_BG, font=("Consolas", 9))
        menu.add_command(label="[REFRESH]", command=self.refresh_balance)
        menu.add_command(label="[SETUP]", command=self.open_settings)
        menu.add_separator()
        self._top_var = tk.BooleanVar(value=True)
        menu.add_checkbutton(label="Always On Top", variable=self._top_var,
                             command=lambda: self.root.attributes("-topmost", self._top_var.get()))
        menu.add_separator()
        menu.add_command(label="Reset Stats", command=self._reset_stats)
        menu.add_command(label="Hide (Ctrl+Alt+D)", command=self.hide_widget)
        menu.add_command(label="[EXIT]", command=self.root.quit)

        for w in (self.root, self.content):
            w.bind("<Button-3>", lambda e: menu.tk_popup(e.x_root, e.y_root))

        self.root.bind("<Configure>", lambda e: self._draw_progress(
            self._cur_ratio if hasattr(self, '_cur_ratio') else 0))

    def _reset_stats(self):
        if self.balance_data:
            self.initial_balance = self.balance_data["balance"]
            save_state({"initial_balance": self.initial_balance})
            self.status_var.set("统计已重置")
            self.refresh_balance()

    # ── 显示/隐藏 ──
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
        if self._hotkey_ok and platform.system() == "Windows":
            try:
                import ctypes
                from ctypes import wintypes
                u = ctypes.windll.user32
                WM_HOTKEY = 0x0312
                hwnd = self._get_hwnd()
                msg = wintypes.MSG()
                while u.PeekMessageW(ctypes.byref(msg), hwnd, WM_HOTKEY, WM_HOTKEY, 1):
                    if msg.wParam == HOTKEY_ID:
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
            self.balance_var.set("--.--")
            self.balance_label.configure(fg=C_ERROR)
            self.sub_var.set("⚠  " + error)
            self.consume_var.set(""); self.topped_var.set(""); self.token_var.set("")
            self.status_var.set(f"ERR: {error}")
            return

        info = parse_balance(data)
        self.balance_data = info
        bal = info["balance"]
        topped = info["topped"]

        # 首次运行记录初始余额
        if self.initial_balance is None:
            self.initial_balance = bal
            save_state({"initial_balance": bal})

        # 消耗统计（从本脚本启动开始）
        consumed = max(0, self.initial_balance - bal)
        consumed_pct = (consumed / self.initial_balance * 100) if self.initial_balance > 0 else 0

        # 进度条：充值余额占比
        self._cur_ratio = (topped / bal) if bal > 0 else 0

        # Token 估算
        remain_tokens = int(bal / TOKEN_PRICE) if TOKEN_PRICE > 0 else 0
        if remain_tokens >= 1_000_000:
            token_str = f"≈ {remain_tokens/1_000_000:.1f}M"
        elif remain_tokens >= 1_000:
            token_str = f"≈ {remain_tokens/1_000:.0f}K"
        else:
            token_str = f"≈ {remain_tokens}"

        if bal < 0:
            color, status = C_ERROR, "数据异常"
        elif bal < 1:
            color, status = C_WARN, "余额不足"
        elif not info["is_available"]:
            color, status = C_ERROR, "不可用"
        else:
            color, status = C_CYAN, "正常"

        self.balance_var.set(f"{bal:.2f}")
        self.balance_label.configure(fg=color)
        self.sub_var.set(f"CNY  ·  {status}")
        self.consume_var.set(f"消耗 {consumed:.2f} ({consumed_pct:.1f}%)" if consumed > 0 else "消耗 0.00")
        self.topped_var.set(f"充值 {topped:.2f}")
        self.token_var.set(f"≈ {token_str}")
        self._draw_progress(self._cur_ratio)
        self._update_time()

    def _update_time(self):
        self.status_var.set(f"更新 {datetime.now():%H:%M:%S}")

    def _auto_refresh(self):
        self.refresh_balance()
        self.root.after(REFRESH_INTERVAL * 1000, self._auto_refresh)

    def open_settings(self):
        SettingsDialog(self.root, self.config.get("api_key", ""), self._on_save_key)

    def _on_save_key(self, key):
        self.config["api_key"] = key
        save_config(self.config)
        self.initial_balance = None
        self.refresh_balance()


# ═══════════════════════════════════════════════════════════
#  Canvas 圆角矩形补丁
# ═══════════════════════════════════════════════════════════

def _patch_canvas():
    def _rounded_rect(self, x1, y1, x2, y2, r, **kw):
        r = min(r, (x2 - x1) // 2, (y2 - y1) // 2)
        pts = []
        for px, py in [(x1+r,y1),(x2-r,y1),(x2,y1+r),(x2,y2-r),(x2-r,y2),(x1+r,y2),(x1,y2-r),(x1,y1+r)]:
            pts += [px, py]
        return self.create_polygon(pts, smooth=True, **kw)
    tk.Canvas.create_rounded_rect = _rounded_rect


_patch_canvas()


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
