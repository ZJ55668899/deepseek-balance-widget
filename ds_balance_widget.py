#!/usr/bin/env python3
"""
DeepSeek Balance Widget — 桌面余额挂件
实时显示 DeepSeek API 账户余额，自动刷新，置顶显示

启动方式：
  pythonw ds_balance_widget.py     # 无窗口启动（推荐）
  python  ds_balance_widget.py     # 带调试控制台启动
  或双击「启动余额挂件.bat」
"""

import tkinter as tk
import requests
import json
import os
import sys
import threading
import tempfile
import atexit
from datetime import datetime
from pathlib import Path

# ─── 配置 ───────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent.resolve()
CONFIG_DIR = SCRIPT_DIR / ".ds_widget"
CONFIG_DIR.mkdir(exist_ok=True)
CONFIG_FILE = CONFIG_DIR / "config.json"
LOCK_FILE = Path(tempfile.gettempdir()) / ".ds_widget.lock"
API_URL = "https://api.deepseek.com/user/balance"
REFRESH_INTERVAL = 30  # 秒

# ─── 深色主题色板 ──────────────────────────────────────────
C_BG        = "#0d1117"
C_CARD      = "#161b22"
C_ACCENT    = "#00d4aa"
C_WARN      = "#f0883e"
C_ERROR     = "#f85149"
C_TEXT      = "#e6edf3"
C_MUTED     = "#8b949e"
C_TITLE_BG  = "#0d1117"


# ═══════════════════════════════════════════════════════════
#  单例锁（文件锁 + PID 检查，兼容 Windows / Linux）
# ═══════════════════════════════════════════════════════════

def try_lock() -> bool:
    """
    尝试获取单例锁。
    返回 True  → 自己是第一个实例
    返回 False → 已有实例在运行，已通知它显示
    """
    try:
        if LOCK_FILE.exists():
            content = LOCK_FILE.read_text().strip()
            if content and content.isdigit():
                pid = int(content)
                if _pid_alive(pid):
                    _signal_show()   # 通知老实例显示自己
                    return False

        # 写入自己的 PID
        LOCK_FILE.write_text(str(os.getpid()), encoding="utf-8")
        return True
    except Exception:
        # 出错时保守处理：当作新实例正常启动
        return True


def _pid_alive(pid: int) -> bool:
    """检查给定 PID 是否还在运行"""
    if os.name == "nt":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(0x0400, False, pid)  # PROCESS_QUERY_INFORMATION
            if handle:
                kernel32.CloseHandle(handle)
                return True
        except Exception:
            pass
        return False
    else:
        # Linux / macOS
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def _signal_show():
    """写信号文件，通知已有实例显示自己"""
    try:
        (CONFIG_DIR / "show.signal").write_text("1", encoding="utf-8")
    except Exception:
        pass


def release_lock():
    """退出时清理锁文件（仅当是自己的锁）"""
    try:
        if LOCK_FILE.exists() and LOCK_FILE.read_text().strip() == str(os.getpid()):
            LOCK_FILE.unlink(missing_ok=True)
    except Exception:
        pass


atexit.register(release_lock)


# ═══════════════════════════════════════════════════════════
#  API 相关
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
        CONFIG_FILE.write_text(
            json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except Exception as e:
        print(f"[ds_widget] 保存配置失败: {e}")


def fetch_balance(api_key: str):
    """调用 DeepSeek API 获取余额（在子线程中调用）"""
    if not api_key:
        return None, "请先设置 API Key"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }
    try:
        resp = requests.get(API_URL, headers=headers, timeout=10)
        if resp.status_code == 200:
            return resp.json(), None
        elif resp.status_code == 401:
            return None, "API Key 无效"
        elif resp.status_code == 429:
            return None, "请求过于频繁"
        else:
            return None, f"HTTP {resp.status_code}"
    except requests.exceptions.Timeout:
        return None, "连接超时"
    except requests.exceptions.ConnectionError:
        return None, "网络不可达"
    except Exception as e:
        return None, str(e)


def parse_balance(data: dict) -> tuple:
    """
    解析余额响应。
    返回 (balance_float, is_available, detail_text)
    """
    if not data:
        return 0.0, True, "无数据"

    is_available = bool(data.get("is_available", True))

    infos = data.get("balance_infos")
    if infos and isinstance(infos, list):
        total = 0.0
        parts = []
        for info in infos:
            tb = float(info.get("total_balance", 0))
            total += tb
            topped = float(info.get("topped_up_balance", 0))
            granted = float(info.get("granted_balance", 0))
            if topped or granted:
                parts.append(f"充值 {topped:.2f} | 赠送 {granted:.2f}")
        detail = "  ".join(parts) if parts else ""
        return total, is_available, detail

    # 兼容: { "balance": 123.45, "is_available": true }
    if "balance" in data and data["balance"] is not None:
        bal = float(data["balance"])
        avail = bool(data.get("is_available", data.get("available", True)))
        return bal, avail, ""

    # 兜底
    for key in ("available_balance", "remaining", "credit"):
        if key in data:
            try:
                return float(data[key]), True, ""
            except (ValueError, TypeError):
                pass

    return 0.0, True, "未知响应格式"


# ═══════════════════════════════════════════════════════════
#  设置对话框
# ═══════════════════════════════════════════════════════════

class SettingsDialog:
    def __init__(self, parent, current_key: str, callback):
        self.callback = callback
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("设置")
        self.dialog.configure(bg=C_BG)
        self.dialog.geometry("420x200")
        self.dialog.resizable(False, False)
        self.dialog.attributes("-topmost", True)
        self.dialog.transient(parent)
        self.dialog.grab_set()

        # 居中
        self.dialog.update_idletasks()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        px, py = parent.winfo_x(), parent.winfo_y()
        dw, dh = 420, 200
        x = px + (pw - dw) // 2
        y = py + (ph - dh) // 2
        self.dialog.geometry(f"+{x}+{y}")

        tk.Label(
            self.dialog, text="DeepSeek API 设置",
            bg=C_BG, fg=C_TEXT,
            font=("Microsoft YaHei", 12, "bold"),
        ).pack(pady=(16, 8))

        frame = tk.Frame(self.dialog, bg=C_BG)
        frame.pack(pady=4)
        tk.Label(frame, text="API Key:", bg=C_BG, fg=C_TEXT,
                 font=("Microsoft YaHei", 10)).pack(side="left")

        self.entry = tk.Entry(
            frame, width=36, show="●",
            bg=C_CARD, fg=C_TEXT, insertbackground=C_TEXT,
            font=("Consolas", 10), relief="flat", bd=8,
        )
        self.entry.insert(0, current_key)
        self.entry.pack(side="left", padx=(8, 4))

        self.show_btn = tk.Button(
            frame, text="👁", command=self.toggle_show,
            bg=C_CARD, fg=C_MUTED, bd=0, cursor="hand2",
        )
        self.show_btn.pack(side="left")

        tk.Label(
            self.dialog,
            text="在 platform.deepseek.com/api_keys 获取",
            bg=C_BG, fg=C_MUTED,
            font=("Microsoft YaHei", 8),
        ).pack(pady=(0, 8))

        btn_frame = tk.Frame(self.dialog, bg=C_BG)
        btn_frame.pack(pady=6)

        for text, bg, fg, cmd in [
            ("保存", C_ACCENT, "#0d1117", self.save),
            ("取消", "#21262d", C_TEXT, self.dialog.destroy),
        ]:
            tk.Button(
                btn_frame, text=text, bg=bg, fg=fg, bd=0,
                padx=20, pady=4, cursor="hand2",
                font=("Microsoft YaHei", 9), command=cmd,
            ).pack(side="left", padx=6)

    def toggle_show(self):
        if self.entry.cget("show") == "●":
            self.entry.config(show="")
            self.show_btn.config(text="🙈")
        else:
            self.entry.config(show="●")
            self.show_btn.config(text="👁")

    def save(self):
        key = self.entry.get().strip()
        if key:
            self.callback(key)
        self.dialog.destroy()


# ═══════════════════════════════════════════════════════════
#  主挂件
# ═══════════════════════════════════════════════════════════

class BalanceWidget:
    def __init__(self):
        self.config = load_config()
        self.error = None
        self.detail_text = ""

        self.root = tk.Tk()
        self.root.title("DeepSeek Balance Widget")
        self.setup_window()
        self.setup_ui()
        self.bind_events()

        # 定时检查信号文件（被另一个实例唤醒）
        self._poll_signal()

        self.root.after(500, self.refresh_balance)
        self.schedule_auto_refresh()
        self.root.mainloop()

    # ── 窗口属性 ─────────────────────────────────────────────
    def setup_window(self):
        w, h = 240, 190
        sw = self.root.winfo_screenwidth()
        x = sw - w - 30
        y = 90

        self.root.overrideredirect(True)
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.94)
        self.root.configure(bg=C_BG)

        # 不在任务栏显示
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
            style |= 0x00000080  # WS_EX_TOOLWINDOW
            ctypes.windll.user32.SetWindowLongW(hwnd, -20, style)
        except Exception:
            pass

    # ── UI 构建 ─────────────────────────────────────────────
    def setup_ui(self):
        # 标题栏
        self.title_bar = tk.Frame(self.root, bg=C_TITLE_BG, height=28)
        self.title_bar.pack(fill="x")
        self.title_bar.pack_propagate(False)

        tk.Label(
            self.title_bar, text="DeepSeek 余额",
            bg=C_TITLE_BG, fg=C_MUTED,
            font=("Microsoft YaHei", 9),
        ).pack(side="left", padx=10, pady=4)

        hide_btn = tk.Button(
            self.title_bar, text="—",
            bg=C_TITLE_BG, fg=C_MUTED, bd=0, cursor="hand2",
            font=("Segoe UI", 10), command=self.hide_widget,
        )
        hide_btn.pack(side="right", padx=2)

        close_btn = tk.Button(
            self.title_bar, text="✕",
            bg=C_TITLE_BG, fg=C_MUTED, bd=0, cursor="hand2",
            font=("Segoe UI", 10), command=self.root.quit,
        )
        close_btn.pack(side="right", padx=(2, 6))

        # 余额显示
        self.content = tk.Frame(self.root, bg=C_BG)
        self.content.pack(fill="both", expand=True)

        self.balance_var = tk.StringVar(value="---")
        self.balance_label = tk.Label(
            self.content, textvariable=self.balance_var,
            bg=C_BG, fg=C_ACCENT,
            font=("Segoe UI", 38, "bold"),
        )
        self.balance_label.pack(pady=(16, 0))

        self.sub_var = tk.StringVar(value="CNY  ·  等待刷新")
        tk.Label(
            self.content, textvariable=self.sub_var,
            bg=C_BG, fg=C_MUTED,
            font=("Microsoft YaHei", 9),
        ).pack()

        self.status_var = tk.StringVar(value="")
        tk.Label(
            self.content, textvariable=self.status_var,
            bg=C_BG, fg=C_MUTED, font=("Consolas", 8),
        ).pack(pady=(4, 0))

        # 底部操作栏
        bottom = tk.Frame(self.root, bg=C_BG)
        bottom.pack(fill="x", side="bottom", pady=(0, 6))

        tk.Button(
            bottom, text="⟳ 刷新",
            bg=C_BG, fg=C_MUTED, bd=0, cursor="hand2",
            font=("Microsoft YaHei", 8),
            activebackground=C_CARD, activeforeground=C_TEXT,
            command=self.refresh_balance,
        ).pack(side="left", padx=8)

        tk.Button(
            bottom, text="⚙ 设置",
            bg=C_BG, fg=C_MUTED, bd=0, cursor="hand2",
            font=("Microsoft YaHei", 8),
            activebackground=C_CARD, activeforeground=C_TEXT,
            command=self.open_settings,
        ).pack(side="right", padx=8)

        if not self.config.get("api_key"):
            self.status_var.set("右键 → 设置 → 输入 API Key")

    # ── 交互事件 ────────────────────────────────────────────
    def bind_events(self):
        drag = {"x": 0, "y": 0}

        def on_press(e):
            drag["x"] = e.x
            drag["y"] = e.y

        def on_drag(e):
            x = self.root.winfo_x() + (e.x - drag["x"])
            y = self.root.winfo_y() + (e.y - drag["y"])
            self.root.geometry(f"+{x}+{y}")

        for w in (self.title_bar, self.content, self.balance_label):
            w.bind("<Button-1>", on_press)
            w.bind("<B1-Motion>", on_drag)

        self.title_bar.bind("<Double-Button-1>", lambda e: self.open_settings())
        self.root.bind("<Escape>", lambda e: self.root.quit())

        # 右键菜单
        menu = tk.Menu(self.root, tearoff=0, bg=C_CARD, fg=C_TEXT,
                       activebackground=C_ACCENT, activeforeground=C_BG,
                       font=("Microsoft YaHei", 9))
        menu.add_command(label="⟳ 刷新", command=self.refresh_balance)
        menu.add_command(label="⚙ 设置", command=self.open_settings)
        menu.add_separator()
        self._top_var = tk.BooleanVar(value=True)
        menu.add_checkbutton(
            label="置顶显示", variable=self._top_var,
            command=lambda: self.root.attributes("-topmost", self._top_var.get()),
        )
        menu.add_separator()
        menu.add_command(label="隐藏（双击启动脚本可呼出）", command=self.hide_widget)
        menu.add_command(label="✕ 退出", command=self.root.quit)

        for w in (self.root, self.title_bar, self.content, self.balance_label):
            w.bind("<Button-3>", lambda e: menu.tk_popup(e.x_root, e.y_root))

    # ── 显示/隐藏 ───────────────────────────────────────────
    def hide_widget(self):
        self.root.withdraw()

    def show_widget(self):
        self.root.deiconify()
        self.root.lift()
        self.refresh_balance()

    def _poll_signal(self):
        """每 2 秒检查信号文件（被另一个实例唤醒）"""
        signal_file = CONFIG_DIR / "show.signal"
        if signal_file.exists():
            try:
                signal_file.unlink(missing_ok=True)
                self.show_widget()
            except Exception:
                pass
        self.root.after(2000, self._poll_signal)

    # ── 数据获取 ─────────────────────────────────────────────
    def refresh_balance(self):
        api_key = self.config.get("api_key", "")
        if not api_key:
            self.update_display(None, "请设置 API Key")
            return

        def fetch_thread():
            data, err = fetch_balance(api_key)
            self.root.after(0, self.update_display, data, err)

        threading.Thread(target=fetch_thread, daemon=True).start()

    def update_display(self, data, error):
        self.error = error

        if error:
            self.balance_var.set("--.--")
            self.balance_label.configure(fg=C_ERROR)
            self.sub_var.set("CNY")
            self.status_var.set(f"⚠ {error}")
            self._update_time()
            return

        balance, available, detail = parse_balance(data)
        self.detail_text = detail

        if balance < 0:
            self.balance_var.set("--.--")
            color, status = C_ERROR, "数据异常"
        elif balance < 1:
            color, status = C_WARN, "余额不足"
        elif not available:
            color, status = C_ERROR, "账户不可用"
        else:
            color, status = C_ACCENT, "正常"

        self.balance_var.set(f"{balance:.2f}")
        self.balance_label.configure(fg=color)
        self.sub_var.set(f"CNY  ·  {status}")
        self.status_var.set(detail if detail else "")
        self._update_time()

    def _update_time(self):
        now = datetime.now().strftime("%H:%M:%S")
        full = self.status_var.get()
        gap = "  " if full else ""
        self.status_var.set(f"{full}{gap}更新 {now}")

    def schedule_auto_refresh(self):
        self.refresh_balance()
        self.root.after(REFRESH_INTERVAL * 1000, self.schedule_auto_refresh)

    # ── 设置 ─────────────────────────────────────────────────
    def open_settings(self):
        SettingsDialog(self.root, self.config.get("api_key", ""), self._on_save_key)

    def _on_save_key(self, key):
        self.config["api_key"] = key
        save_config(self.config)
        self.refresh_balance()


# ═══════════════════════════════════════════════════════════
#  启动入口
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
        log_path = SCRIPT_DIR / "ds_widget_error.log"
        try:
            log_path.write_text(
                f"时间: {datetime.now()}\n"
                f"错误: {e}\n"
                f"{traceback.format_exc()}",
                encoding="utf-8",
            )
        except Exception:
            pass
        # 如果是在控制台运行，打印错误
        print(f"[ds_widget] 启动失败: {e}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
