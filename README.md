# FileHelper ｜ 局域网双向原画与剪贴板传输助手

<p align="left">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-07c160.svg" alt="License"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.10+-007aff.svg" alt="Python"></a>
  <img src="https://img.shields.io/badge/Platform-Windows%20%E2%86%94%20iPhone-1d1d1f.svg" alt="Platform">
</p>

在同一 Wi-Fi 局域网下，提供类似微信「文件传输助手」直觉体验的 **Windows ⇄ iPhone 双向原画、大文件与剪贴板传输工具**。不经过外网服务器、默认 100% 原图原片无损直传、电脑大文件零拷贝流式读取，并内置轻量级微信风独立看图器与框选标注工具。

---

## 一、 核心特性与对比

| 传统方式 | 常见痛点 | FileHelper 方案 |
| :--- | :--- | :--- |
| **微信文件传输助手** | 图片/视频默认压缩、大体积文件受限、需登录账号并走公网中转 | **纯局域网高速直连**，默认 **100% 原始画质**，几十 GB 的 4K/60fps `.mp4` / `.mov` 秒级流式响应 |
| **网盘 / iCloud** | 先上传云端再下载到另一端，受限于外网宽带上传速率与云空间配额 | **零外网流量消耗**，直接跑满本地路由器 Wi-Fi 带宽 |
| **单向局域网投递脚本** | 仅支持单向发文件，不支持双向发文字链接、粘贴截图或看图框选标注 | **完整双向对话流**：文字/链接一键复制、电脑 `Ctrl+V` 输入框草稿图预览、双端原图互传、内置看图与框选裁剪编辑 |

### 底层架构原则
1. **磁盘文件零拷贝流（Zero-Copy Range Streaming）**：电脑拖入文件或文件夹时，仅记录磁盘绝对路径，不复制临时文件；手机端拉取时直接从原路径按 `512 KB` 分块流式读取（完整支持 `HTTP 206 Partial Content` 断点续传与视频边下边播）。
2. **本地持久化与一键彻底擦除**：日常开关窗口自动保留历史记录（存放于本地 `data/` 目录，Git 自动忽略）；点击右上角 **「清空」** 时，双端列表与本地 `data/` 历史数据、二进制缓存同步 **100% 物理删除**，不留任何残余。

---

## 二、 界面预览

| 空状态（极简待命） | 双向对话与草稿粘贴 | 毛玻璃扫码连接 | 独立看图与顶栏框选标注 |
| :---: | :---: | :---: | :---: |
| <img src="assets/preview_empty.png" width="205" alt="空状态"> | <img src="assets/preview_queue.png" width="205" alt="双向对话与草稿粘贴"> | <img src="assets/preview_modal.png" width="205" alt="手机扫码连接"> | <img src="assets/preview_viewer.png" width="205" alt="看图与顶栏框选编辑"> |

---

## 三、 快速安装与使用（Windows 10 / 11）

### 方式 A：普通用户免环境安装（推荐，无需配置 Python）
前往仓库右侧 [**Releases**](https://github.com/aodilab/FileHelper/releases) 页面，按需求任选一种下载：

1. **绿色免安装版（`FileHelper-win64-portable.zip`）**：下载解压后，直接双击文件夹内的 **`FileHelper.exe`** 即可使用（本地记录保存在同目录 `data/`，删除文件夹即彻底卸载）。
2. **标准安装包（`FileHelper-Setup.exe`）**：双击运行安装向导，可自动创建桌面快捷方式（支持把文件直接拖到桌面图标上快速发送）并自动添加 `8899` 端口防火墙放行规则。

> **首次运行提示**：
> - 若 Windows 弹出 **「Windows 已保护你的电脑」（SmartScreen 提示）**，点击 **「更多信息」 → 「仍要运行」** 即可（开源项目未购买商业代码签名证书，源码完全公开可查）。
> - 若系统弹出 **Windows 防火墙警报**，请勾选当前网络并点击 **「允许访问」**，否则同 Wi-Fi 下的 iPhone 将无法连接。

### 方式 B：电脑端高频交互
- **发文件 / 文件夹**：点击左下角 `+` 选择，或直接将文件拖拽进窗口，亦可直接把文件拖到桌面的 **「文件传输助手」图标** 上（单实例自动唤醒并入队）。
- **发截图（微信同款草稿预览）**：截图后按 `Ctrl+V`，缩略草稿图直接嵌入底部输入框内（可点击放大预览/标注，按 `Backspace` 或点右上角 `×` 移除，按 `Enter` 或点「发送」发出）。
- **发文字 / 网址**：底部输入框输入或粘贴文本，回车即发；点击任意文字气泡一键复制。
- **独立看图与框选编辑**：点击聊天流中的任意图片打开独立查看器（滚轮指针缩放、双击 `1:1`、左右键切图）；点击顶栏 **编辑图标** 原地切换为微信 PC 风格单排工具栏（方框、圆框、箭头、画笔、马赛克、裁剪、撤销、另存为），点击 **「完成」** 自动写入系统剪贴板。

---

## 四、 iPhone 端连接与收发方式

### 方式一：Safari 扫码 / 添加到主屏幕（推荐，完整双向聊天体验）
1. 点击电脑端右上角 **「手机连接」** 打开二维码弹窗；
2. 用 iPhone 原生相机扫码并在 **Safari** 中打开（可点击 Safari 底部分享按钮 → **「添加到主屏幕」**，获得独立全屏 Web App 图标）；
3. **手机端交互**：
   - **发原图 / 视频 / 文件**：点击底栏右侧 `+` 呼出 iOS 原生菜单（`照片图库` / `拍照或录像` / `选取文件`），在系统相册中勾选后点右上角对勾 `✓` **立即一步直发**（无二次确认页，默认 100% 原始画质上传）；
   - **收图片 / 改图 / 删记录**：轻点图片全屏查看，**长按任意气泡或图片** 呼出微信同款深色菜单（`保存到相册` / `复制` / `编辑` / `下载` / `删除`）。

### 方式二：iOS「快捷指令」桌面一键直存相册（适合批量收电脑原片）
只需配置 2 个动作，点击手机桌面指令图标即可把电脑队列中的待发视频/原图直接无损存入系统相册：
1. 打开 iPhone **「快捷指令」** App，点击右上角 `+` 新建指令：
   - **动作 1**：添加 **「获取 URL 的内容」**，地址填 `http://<电脑局域网IP>:8899/api/latest`；
   - **动作 2**：添加 **「存储到相簿」**（将 `URL 的内容` 存储到 `最近项目`）。
2. 重命名并选择 **「添加到主屏幕」**，首次运行允许局域网与照片权限即可。

---

## 五、 目录架构与命令速查

```text
├── build.py                   # 统一启动与构建入口
├── requirements.txt           # 运行依赖 (Pillow / qrcode / tkinterdnd2 / pywin32)
├── config/
│   └── settings.py            # 端口、窗口尺寸、MIME 兜底映射、校准色彩 Token 与行数红线
├── src/
│   ├── core/
│   │   ├── queue_manager.py   # 线程安全队列、data/ 本地持久化、系统剪贴板与单实例 IPC
│   │   └── http_server.py     # 端口独占保护、HTTP 206 Range 分块流与双向 REST 接口
│   └── ui/
│       ├── components.py      # 2x 超采样抗锯齿绘图原语与圆角缩略图缓存
│       ├── chat_items.py      # 聊天气泡、自适应图片缩略图、双行文件卡片与悬停动作排版
│       ├── renderer.py        # 桌面主窗口、输入框草稿图与毛玻璃扫码弹窗渲染器
│       ├── desktop_app.py     # TkinterDnD 窗口控制、剪贴板监听与版本号状态轮询
│       ├── image_viewer.py    # 微信风独立图片查看器（对称留白、滚轮缩放、自适应居中）
│       └── image_editor.py    # 顶栏单排矢量标注与裁剪会话（方框/圆框/箭头/画笔/马赛克/裁剪）
├── templates/
│   └── mobile_portal.html     # iPhone Safari / Web App 双向门户、右侧 + 一步选图直发与画布编辑器
├── scripts/
│   ├── icon_builder.py        # 多尺寸 ICO/PNG/iOS Touch Icon 与桌面快捷方式生成
│   ├── packager.py            # PyInstaller 绿色版压缩包与 Inno Setup 安装包构建
│   ├── installer.iss          # Windows 安装向导脚本（含桌面图标与 8899 端口放行）
│   └── visual_audit.py        # 桌面五态快照渲染、README 预览图同步与代码行数审计
└── assets/                    # 应用图标与界面预览图
```

### 开发者源码运行与打包
- **环境要求**：Windows 10 / 11，Python 3.10+。

```powershell
git clone https://github.com/aodilab/FileHelper.git
cd FileHelper
pip install -r requirements.txt
python build.py --shortcut   # 创建桌面快捷方式
python build.py              # 启动桌面端
```

| 命令 | 说明 |
| :--- | :--- |
| `python build.py` | 启动桌面端（若已有实例运行则自动前置唤醒） |
| `python build.py <文件路径...>` | 启动或唤醒现有窗口，并将指定文件/文件夹加入队列 |
| `python build.py --shortcut` | 在 Windows 桌面创建 `文件传输助手.lnk` 快捷方式 |
| `python build.py --icon` | 重新生成 `assets/` 下的多尺寸桌面与 iOS 图标 |
| `python build.py --package` | 使用 PyInstaller 打包绿色免安装 `.zip`（若本机安装 Inno Setup 6 则同步生成 `Setup.exe`） |
| `python build.py --audit` | 生成桌面五态自审快照并校验全项目代码行数规范 |
| `python build.py --all` | 依次执行图标生成、快捷方式更新、README 预览图同步与代码审计 |

---

## 六、 常见问题排查

1. **手机扫码打不开网页，或快捷指令提示连接超时？**
   - 确认电脑与 iPhone 连接在同一局域网下（未开启 AP 隔离或全局 TUN 代理拦截局域网流量）；
   - 若 Windows 将当前 Wi-Fi 识别为「公用网络」，系统防火墙可能拦截 `8899` 端口入站请求。可在 Windows 网络设置中将其切换为 **「专用网络」**，或在防火墙入站规则中放行 Python / `8899` 端口。
2. **固定端口 `8899` 被其他本地进程占用怎么办？**
   - FileHelper 启动时会自动检测并清理占用 `8899` 的非本程序残留进程（`_reclaim_port`），同时开启 Windows 内核级 `SO_EXCLUSIVEADDRUSE` 套接字独占锁，确保手机书签与快捷指令中的 `:8899` 地址长期稳定可用。
