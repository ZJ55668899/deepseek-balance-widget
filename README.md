# ⚡ DeepSeek Balance Widget

桌面余额挂件 — 实时显示 DeepSeek API 账户余额与消耗进度。

![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey)
![Dependencies](https://img.shields.io/badge/dependencies-zero-brightgreen)

---

## ✨ 功能

| 功能 | 说明 |
|------|------|
| 💰 **余额显示** | 实时查询 DeepSeek 账户余额 |
| 📊 **消耗进度条** | 可视化已用额度占总充值额的比例 |
| 🔄 **自动刷新** | 每 30 秒自动更新 |
| ⌨️ **全局热键** | `Ctrl + Alt + D` 随时显示/隐藏窗口 |
| 🎨 **赛博科技风** | 深色主题，电光蓝配色 |
| 🪟 **置顶显示** | 始终在其他窗口之上，可拖动 |
| 📦 **零依赖** | 仅需 Python 3 标准库，无需 pip install |

## 📷 预览

```
┌─ ⚡ DeepSeek  v1 ── ✕┐
│                        │
│      ¥88.88            │
│   CNY · 正常           │
│                        │
│  ┌─────────────────┐   │
│  │     42.9%       │   │
│  └─────────────────┘   │
│  已用 66.66 | 42.9%    │
│                   总额  │
│  更新 14:30    [SETUP]  │
└────────────────────────┘
```

## 🚀 快速开始

### 环境要求

- **Windows** 系统（Linux/macOS 未测试但理论上可运行）
- **Python 3.8+** 已安装并加入 PATH

### 下载

```bash
git clone https://github.com/ZJ55668899/deepseek-balance-widget.git
cd deepseek-balance-widget
```

或者直接下载 ZIP 解压。

### 启动

**方式一：双击运行（推荐）**

双击 `start_widget.bat`，后台无窗口启动。

**方式二：命令行**

```bash
pythonw ds_balance_widget.py      # 后台无窗口
python  ds_balance_widget.py      # 带控制台输出
```

## 🔑 配置 API Key

1. 打开 [platform.deepseek.com/api_keys](https://platform.deepseek.com/api_keys)
2. 创建一个 API Key
3. 右键挂件 → **[SETUP]** → 输入 API Key → 保存

API Key 将保存在本地的 `.ds_widget/config.json` 文件中。

## ⌨️ 操作

| 操作 | 效果 |
|------|------|
| **鼠标拖动** | 移动挂件位置 |
| **右键菜单** | 刷新 / 设置 / 置顶 / 隐藏 / 退出 |
| **双击标题栏** | 打开设置 |
| **— 按钮** | 隐藏窗口 |
| **Ctrl + Alt + D** | 全局热键，显示/隐藏窗口 |
| **Esc** | 退出 |

## 📁 文件结构

```
deepseek-balance-widget/
├── ds_balance_widget.py    # 主程序
├── start_widget.bat        # 启动脚本（双击运行）
├── .ds_widget/
│   └── config.json         # API Key 配置文件（自动生成）
└── README.md
```

## 📊 数据说明

| 数据项 | 来源 |
|--------|------|
| 当前余额 | DeepSeek `/user/balance` API |
| 已用额度 | `(充值总额 + 赠送总额) - 当前余额` |
| 消耗比例 | `已用额度 / 总额` × 100% |

> **Token 用量**：DeepSeek 未提供查询历史 Token 用量的公开 API，如需查看请前往 [DeepSeek 控制台](https://platform.deepseek.com) → 用量 → 导出 CSV。

## 🛠 技术细节

- 纯 **Python 3 标准库**（tkinter / urllib / json / threading），零外部依赖
- 全局热键通过 Windows `RegisterHotKey` API 实现
- 单例运行通过文件锁 + PID 检查确保
- 窗口采用 `overrideredirect` + `WS_EX_TOOLWINDOW` 实现无边框置顶挂件

## 📄 License

MIT
