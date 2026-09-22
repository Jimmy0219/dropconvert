#!/usr/bin/env python3
"""轉檔工具的桌面 App：macOS 原生視窗（WKWebView），介面沿用 ui.html。

平常雙擊 `轉檔工具.app` 啟動（用 ./make_app.sh 產生）；開發時也可以直接執行：

    uv run app.py
"""

from __future__ import annotations

import threading
from pathlib import Path

import webview

import convert
import ui

APP_NAME = "轉檔工具"
ICON = Path(__file__).with_name("AppIcon.icns")


def main() -> None:
    convert.ensure_folders()
    # 視窗內容仍由 ui.py 的本機伺服器提供；埠號交給系統挑，使用者看不到也不用管
    server = ui.make_server(0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/"

    window = webview.create_window(
        APP_NAME, url,
        width=980, height=860, min_size=(640, 560),
        background_color="#f5f5f3",
    )

    def on_closing():
        if not ui.runner.running:
            return True
        leave = window.create_confirmation_dialog(
            "正在轉換中",
            "確定要關閉嗎？\n目前這個檔案會轉完再結束，其餘的留在「待轉檔」下次再轉。")
        if leave:
            ui.runner.cancel = True
        return leave

    window.events.closing += on_closing
    webview.start(icon=str(ICON) if ICON.exists() else None)

    # 視窗已經關了；若還有檔案在轉，等它轉完再結束，不留半成品
    if ui.runner.running:
        ui.runner.thread.join()
    server.shutdown()


if __name__ == "__main__":
    main()
