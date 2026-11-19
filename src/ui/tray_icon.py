import ctypes
import ctypes.wintypes as wt
import os
import sys
import threading
import winreg

from config.settings import BASE_DIR, ICON_ICO_PATH, IS_FROZEN

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_RUN_NAME = "FileHelper"
_WM_TRAY = 0x0400 + 20
_NIM_ADD, _NIM_DELETE = 0, 2
_NIF_MESSAGE, _NIF_ICON, _NIF_TIP = 0x01, 0x02, 0x04
_WM_DESTROY, _WM_CLOSE, _WM_LBUTTONUP, _WM_LBUTTONDBLCLK, _WM_RBUTTONUP = 0x0002, 0x0010, 0x0202, 0x0203, 0x0205
_CMD_OPEN, _CMD_AUTOSTART, _CMD_QUIT = 1001, 1002, 1003

_LRESULT = ctypes.c_ssize_t
_WPARAM = ctypes.c_size_t
_LPARAM = ctypes.c_ssize_t
_WNDPROC = ctypes.WINFUNCTYPE(_LRESULT, wt.HWND, wt.UINT, _WPARAM, _LPARAM)

_u32 = ctypes.WinDLL("user32", use_last_error=True)
_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_shell32 = ctypes.WinDLL("shell32", use_last_error=True)
_psapi = ctypes.WinDLL("psapi", use_last_error=True)

_k32.GetCurrentProcess.restype = wt.HANDLE
_k32.GetModuleHandleW.argtypes = [wt.LPCWSTR]
_k32.GetModuleHandleW.restype = wt.HMODULE
_psapi.EmptyWorkingSet.argtypes = [wt.HANDLE]
_psapi.EmptyWorkingSet.restype = wt.BOOL
_u32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, _WPARAM, _LPARAM]
_u32.DefWindowProcW.restype = _LRESULT
_u32.RegisterWindowMessageW.argtypes = [wt.LPCWSTR]
_u32.RegisterWindowMessageW.restype = wt.UINT
_u32.PostMessageW.argtypes = [wt.HWND, wt.UINT, _WPARAM, _LPARAM]
_u32.PostMessageW.restype = wt.BOOL
_u32.LoadImageW.argtypes = [wt.HINSTANCE, wt.LPCWSTR, wt.UINT, ctypes.c_int, ctypes.c_int, wt.UINT]
_u32.LoadImageW.restype = wt.HANDLE
_u32.DestroyIcon.argtypes = [wt.HICON]
_u32.CreatePopupMenu.restype = wt.HMENU
_u32.AppendMenuW.argtypes = [wt.HMENU, wt.UINT, _WPARAM, wt.LPCWSTR]
_u32.SetMenuDefaultItem.argtypes = [wt.HMENU, wt.UINT, wt.UINT]
_u32.TrackPopupMenu.argtypes = [wt.HMENU, wt.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.HWND, wt.LPVOID]
_u32.TrackPopupMenu.restype = wt.BOOL
_u32.DestroyMenu.argtypes = [wt.HMENU]
_u32.SetForegroundWindow.argtypes = [wt.HWND]
_u32.DestroyWindow.argtypes = [wt.HWND]
_u32.PostQuitMessage.argtypes = [ctypes.c_int]
_u32.GetCursorPos.argtypes = [ctypes.POINTER(wt.POINT)]
_u32.GetMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT]
_u32.GetMessageW.restype = wt.BOOL
_u32.TranslateMessage.argtypes = [ctypes.POINTER(wt.MSG)]
_u32.DispatchMessageW.argtypes = [ctypes.POINTER(wt.MSG)]
_u32.DispatchMessageW.restype = _LRESULT


class _WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.UINT), ("style", wt.UINT), ("lpfnWndProc", _WNDPROC),
        ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
        ("hInstance", wt.HINSTANCE), ("hIcon", wt.HICON), ("hCursor", wt.HANDLE),
        ("hbrBackground", wt.HBRUSH), ("lpszMenuName", wt.LPCWSTR),
        ("lpszClassName", wt.LPCWSTR), ("hIconSm", wt.HICON),
    ]


class _NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.DWORD), ("hWnd", wt.HWND), ("uID", wt.UINT), ("uFlags", wt.UINT),
        ("uCallbackMessage", wt.UINT), ("hIcon", wt.HICON), ("szTip", wt.WCHAR * 128),
        ("dwState", wt.DWORD), ("dwStateMask", wt.DWORD), ("szInfo", wt.WCHAR * 256),
        ("uVersion", wt.UINT), ("szInfoTitle", wt.WCHAR * 64), ("dwInfoFlags", wt.DWORD),
        ("guidItem", ctypes.c_byte * 16), ("hBalloonIcon", wt.HICON),
    ]


_shell32.Shell_NotifyIconW.argtypes = [wt.DWORD, ctypes.POINTER(_NOTIFYICONDATAW)]
_shell32.Shell_NotifyIconW.restype = wt.BOOL


def trim_working_set():
    """Ask Windows to page out unused working set pages while hidden in tray."""
    try:
        _psapi.EmptyWorkingSet(_k32.GetCurrentProcess())
    except Exception:
        pass


def _autostart_cmd():
    if IS_FROZEN:
        return f'"{os.path.abspath(sys.executable)}" --tray'
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    exe = pyw if os.path.exists(pyw) else sys.executable
    return f'"{os.path.abspath(exe)}" "{os.path.join(BASE_DIR, "build.py")}" --tray'


def is_autostart_enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_READ) as key:
            val, _ = winreg.QueryValueEx(key, _RUN_NAME)
            return bool(val)
    except OSError:
        return False


def set_autostart(enabled):
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            if enabled:
                winreg.SetValueEx(key, _RUN_NAME, 0, winreg.REG_SZ, _autostart_cmd())
            else:
                try:
                    winreg.DeleteValue(key, _RUN_NAME)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False


class TrayController:
    """Native Win32 system tray icon controller running its own lightweight message loop."""

    def __init__(self, on_show, on_quit, tooltip="文件传输助手 - 局域网服务运行中"):
        self.on_show, self.on_quit, self.tooltip = on_show, on_quit, tooltip[:127]
        self.hwnd, self.hicon, self._thread, self._proc = None, None, None, None
        self._ready = threading.Event()
        self._taskbar_msg = _u32.RegisterWindowMessageW("TaskbarCreated")

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=1.5)

    def _nid(self, flags=0):
        nid = _NOTIFYICONDATAW(cbSize=ctypes.sizeof(_NOTIFYICONDATAW), hWnd=self.hwnd, uID=1, uFlags=flags, uCallbackMessage=_WM_TRAY, hIcon=self.hicon or 0)
        nid.szTip = self.tooltip
        return nid

    def _add_icon(self):
        if self.hwnd:
            _shell32.Shell_NotifyIconW(_NIM_ADD, ctypes.byref(self._nid(_NIF_MESSAGE | _NIF_ICON | _NIF_TIP)))

    def _show_menu(self):
        menu = _u32.CreatePopupMenu()
        if not menu:
            return
        try:
            _u32.AppendMenuW(menu, 0x0000, _CMD_OPEN, "打开文件传输助手")
            _u32.AppendMenuW(menu, 0x0008 if is_autostart_enabled() else 0x0000, _CMD_AUTOSTART, "开机自启动")
            _u32.AppendMenuW(menu, 0x0800, 0, None)
            _u32.AppendMenuW(menu, 0x0000, _CMD_QUIT, "退出")
            _u32.SetMenuDefaultItem(menu, _CMD_OPEN, 0)
            pt = wt.POINT()
            _u32.GetCursorPos(ctypes.byref(pt))
            _u32.SetForegroundWindow(self.hwnd)
            cmd = _u32.TrackPopupMenu(menu, 0x0100 | 0x0002 | 0x0020, pt.x, pt.y, 0, self.hwnd, None)
            _u32.PostMessageW(self.hwnd, 0, 0, 0)
            if cmd == _CMD_OPEN:
                self.on_show()
            elif cmd == _CMD_AUTOSTART:
                set_autostart(not is_autostart_enabled())
            elif cmd == _CMD_QUIT:
                self.on_quit()
        finally:
            _u32.DestroyMenu(menu)

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        if msg == _WM_TRAY:
            ev = lparam & 0xFFFF
            if ev in (_WM_LBUTTONUP, _WM_LBUTTONDBLCLK):
                self.on_show()
            elif ev == _WM_RBUTTONUP:
                self._show_menu()
            return 0
        if msg == self._taskbar_msg and self._taskbar_msg:
            self._add_icon()
            return 0
        if msg == _WM_CLOSE:
            _u32.DestroyWindow(hwnd)
            return 0
        if msg == _WM_DESTROY:
            _shell32.Shell_NotifyIconW(_NIM_DELETE, ctypes.byref(self._nid()))
            _u32.PostQuitMessage(0)
            return 0
        return _u32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _run_loop(self):
        hinst = _k32.GetModuleHandleW(None)
        cls_name = f"FileHelperTray_{os.getpid()}"
        self._proc = _WNDPROC(self._wnd_proc)
        wc = _WNDCLASSEXW(cbSize=ctypes.sizeof(_WNDCLASSEXW), lpfnWndProc=self._proc, hInstance=hinst, lpszClassName=cls_name)
        _u32.RegisterClassExW.argtypes = [ctypes.POINTER(_WNDCLASSEXW)]
        _u32.RegisterClassExW.restype = wt.ATOM
        _u32.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID]
        _u32.CreateWindowExW.restype = wt.HWND
        _u32.RegisterClassExW(ctypes.byref(wc))
        if os.path.exists(ICON_ICO_PATH):
            self.hicon = _u32.LoadImageW(None, ICON_ICO_PATH, 1, 32, 32, 0x0010)
        self.hwnd = _u32.CreateWindowExW(0, cls_name, cls_name, 0, 0, 0, 0, 0, 0, 0, hinst, None)
        self._add_icon()
        self._ready.set()
        msg = wt.MSG()
        while _u32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            _u32.TranslateMessage(ctypes.byref(msg))
            _u32.DispatchMessageW(ctypes.byref(msg))

    def stop(self):
        if self.hwnd:
            _u32.PostMessageW(self.hwnd, _WM_CLOSE, 0, 0)
            if self._thread:
                self._thread.join(timeout=1.0)
            self.hwnd = None
        if self.hicon:
            _u32.DestroyIcon(self.hicon)
            self.hicon = None
