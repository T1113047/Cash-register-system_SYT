# File: [New] cashier/barcode_gun.py
"""条形码扫码枪全局监听模块（纯标准库 ctypes，兼容 Win7 / Python 3.8）。

原理：
    扫码枪本质是键盘设备，扫描后以极快速度(通常 <20ms/键)连续输出条码字符，
    并以回车(Enter)或制表符(Tab)结尾。
    本模块使用全局低级键盘钩子(WH_KEYBOARD_LL)监听按键序列：
      - 相邻字符间隔 < min_interval 秒 => 视为同一次扫描
      - 遇回车/制表符 => 结束一次扫描，回调完整条码
      - 识别成功后【吞掉】结束键，避免焦点控件被回车误触发
    人工打字间隔通常 >100ms，不会误判；粘贴操作不产生键盘序列，天然免疫。

用法：
    listener = BarcodeListener(on_barcode)
    listener.start()
    ...
    listener.stop()
"""

import ctypes
import threading
import time
from ctypes import wintypes
from typing import Callable, Optional

WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
WM_QUIT = 0x0012
VK_RETURN = 0x0D
VK_TAB = 0x09

# vkCode -> 字符映射（覆盖条码常见字符：数字、字母、短横线、下划线、空格）
_KEY_MAP = {}
for _i in range(0x30, 0x3A):  # 主键盘 0-9
    _KEY_MAP[_i] = chr(ord("0") + _i - 0x30)
for _i in range(0x41, 0x5B):  # 主键盘 A-Z
    _KEY_MAP[_i] = chr(ord("A") + _i - 0x41)
for _i in range(0x60, 0x6A):  # 小键盘 0-9
    _KEY_MAP[_i] = chr(ord("0") + _i - 0x60)
_KEY_MAP[0xBD] = "-"  # 主键盘减号
_KEY_MAP[0x6D] = "-"  # 小键盘减号
_KEY_MAP[0xDF] = "_"  # 下划线
_KEY_MAP[0x20] = " "  # 空格

_END_KEYS = (VK_RETURN, VK_TAB)  # 扫描结束键


class _KBDLLHOOKSTRUCT(ctypes.Structure):
    """低级键盘钩子事件结构体。"""

    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class BarcodeListener:
    """全局扫码枪监听器。

    Args:
        on_barcode: 条码回调函数，在钩子线程中被调用（注意线程安全）。
        min_interval: 相邻字符最大间隔秒数，超过则视为新序列，默认 0.06。
        min_length: 条码最小长度，用于过滤误触发，默认 3。
    """

    def __init__(
        self,
        on_barcode: Callable[[str], None],
        min_interval: float = 0.06,
        min_length: int = 3,
    ) -> None:
        self._on_barcode = on_barcode
        self._min_interval = min_interval
        self._min_length = min_length
        self._buffer: list = []
        self._last_time = 0.0
        self._running = False
        self._hook: Optional[int] = None
        self._proc = None  # 钩子回调必须保持引用，防止被 GC 导致崩溃
        self._thread: Optional[threading.Thread] = None

    def start(self) -> bool:
        """启动监听（非阻塞，钩子跑在后台线程）。"""
        if self._running:
            return True
        self._running = True
        self._thread = threading.Thread(target=self._run, name="barcode-listener", daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        """停止监听。"""
        self._running = False
        if self._thread is not None and self._thread.ident:
            try:
                ctypes.windll.user32.PostThreadMessageW(
                    wintypes.DWORD(self._thread.ident), WM_QUIT, 0, 0
                )
            except Exception:
                pass

    # ------------------------------------------------------------------ #
    # 内部实现
    # ------------------------------------------------------------------ #
    def _run(self) -> None:
        """钩子线程主循环（必须跑消息循环，低级钩子依赖它分发事件）。"""
        user32 = ctypes.windll.user32

        HookProc = ctypes.WINFUNCTYPE(
            wintypes.LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
        )

        def proc(n_code: int, w_param: int, l_param: int) -> int:
            eat = False
            if n_code >= 0 and w_param in (WM_KEYDOWN, WM_SYSKEYDOWN):
                data = ctypes.cast(l_param, ctypes.POINTER(_KBDLLHOOKSTRUCT)).contents
                try:
                    eat = self._handle_key(int(data.vkCode))
                except Exception:
                    eat = False
            if not self._running:
                return 1  # 停止阶段拦截所有按键
            if eat:
                return 1  # 吞掉扫码结束键
            return user32.CallNextHookEx(self._hook, n_code, w_param, l_param)

        self._proc = HookProc(proc)
        self._hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, None, 0)
        if not self._hook:
            self._running = False
            return

        msg = wintypes.MSG()
        try:
            while self._running and user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            user32.UnhookWindowsHookEx(self._hook)
            self._hook = None

    def _handle_key(self, vk: int) -> bool:
        """处理按键，返回 True 表示该键应被吞掉。"""
        now = time.time()

        # 结束键：提交条码
        if vk in _END_KEYS:
            if self._buffer:
                code = "".join(self._buffer)
                self._buffer = []
                self._last_time = 0.0
                if len(code) >= self._min_length:
                    try:
                        self._on_barcode(code)
                    except Exception:
                        pass
                    return True  # 识别成功：吞掉结束键，防止误触发焦点控件
                return False  # 长度不足（人工输入）：不吞键，回车正常作用于焦点控件
            return False

        ch = _KEY_MAP.get(vk)
        if ch is None:
            return False

        # 与上一键间隔超时 => 新序列（人工打字不会连续这么快）
        if self._buffer and (now - self._last_time) > self._min_interval:
            self._buffer = []
        self._buffer.append(ch)
        self._last_time = now
        return False
