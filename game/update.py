"""在线更新检查：读取 SHUTTLE 官方版本接口。

官方接口：https://pvz2shuttle.cn/cz/czok.json
返回形如 {"ver": 122, "needDeleteOld": true, "downloadUrl": "https://pvz2shuttle.cn/cz/CDN.zip"}

本模块在后台线程里请求，失败时静默降级（离线也能玩）。
"""
from __future__ import annotations

import json
import ssl
import threading
import urllib.request

from . import config

CZOK_URL = "https://pvz2shuttle.cn/cz/czok.json"


def _ssl_ctx():
    try:
        ctx = ssl.create_default_context()
        # 某些 Windows 机器缺少根证书，降级为不校验（仅用于读取公开版本号）。
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    except Exception:
        return None


def fetch_czok(timeout: float = 5.0) -> dict | None:
    try:
        req = urllib.request.Request(CZOK_URL, headers={"User-Agent": "PvZ2SHUTTLE-Windows/" + config.VERSION})
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_ctx()) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
        if isinstance(data, dict) and "ver" in data:
            return data
    except Exception:
        return None
    return None


class UpdateChecker:
    """非阻塞更新检查。UI 每帧读取 .done / .result。"""

    def __init__(self):
        self.done = False
        self.result: dict | None = None
        self._thread = None

    def start(self):
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        self.result = fetch_czok()
        self.done = True

    @property
    def latest_ver(self) -> int | None:
        if self.result and isinstance(self.result.get("ver"), int):
            return self.result["ver"]
        return None
