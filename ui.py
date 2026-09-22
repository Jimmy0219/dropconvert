#!/usr/bin/env python3
"""轉檔工具的本機網頁介面。

    ./ui.py                 # 啟動並自動打開瀏覽器
    ./ui.py --no-browser    # 只啟動伺服器
    ./ui.py --port 9000     # 指定埠號（預設 8765，被占用就往後找）

網頁只是 convert.py 的另一種操作方式：拖進網頁的檔案會存到「待轉檔/<格式>/」，
按下開始轉換就是逐一呼叫 convert.run_job()。直接把檔案丟進資料夾也照樣會顯示。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import convert
from engines import ROUTES, ConvertError, office_cleanup, unique_path

HOST = "127.0.0.1"   # 只聽本機，區網的其他電腦連不進來
DEFAULT_PORT = 8765
PAGE = Path(__file__).with_name("ui.html")
UPLOAD_CHUNK = 1024 * 1024   # 大影片分塊寫入，不整個讀進 8GB 的記憶體
HISTORY_LIMIT = 200          # 「轉換完成」最多保留幾筆


class Runner:
    """在背景執行緒逐一轉檔，並記錄每個檔案的狀態給網頁查詢。"""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.thread: threading.Thread | None = None
        self.items: dict[str, dict] = {}   # 這一批的狀態，key 是來源檔路徑
        self.history: list[dict] = []      # 開啟期間所有轉好的檔案，跨批次保留
        self.cancel = False

    @property
    def running(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def start(self) -> int:
        """開始轉換目前待轉檔裡可轉的檔案；回傳這次要處理的數量。"""
        with self.lock:
            if self.running:
                return 0
            jobs = [j for j in convert.scan()[0] if j.engine]
            if not jobs:
                return 0
            self.cancel = False
            self.items = {str(j.src): {"status": "queued", "target": j.target} for j in jobs}
            self.thread = threading.Thread(target=self._run, args=(jobs,), daemon=True)
            self.thread.start()
            return len(jobs)

    def _update(self, job: convert.Job, **fields) -> None:
        with self.lock:
            self.items[str(job.src)].update(fields)

    def _run(self, jobs: list[convert.Job]) -> None:
        try:
            for job in jobs:
                if self.cancel:
                    self._update(job, status="cancelled")
                    continue
                if not job.src.exists():
                    self._update(job, status="failed", message="檔案已經被移走了")
                    continue
                self._update(job, status="running", started=time.time())
                try:
                    outputs = convert.run_job(job)
                    self._update(job, status="done")
                    with self.lock:
                        self.history.append({"name": job.src.name, "target": job.target,
                                             "finished": time.time(),
                                             "outputs": [str(p) for p in outputs]})
                        del self.history[:-HISTORY_LIMIT]
                except ConvertError as e:
                    self._update(job, status="failed", message=str(e))
                except Exception as e:
                    # 單一檔案的意外錯誤不該讓整批停下來
                    self._update(job, status="failed",
                                 message=f"未預期的錯誤 {type(e).__name__}: {e}")
        finally:
            office_cleanup()

    def snapshot(self) -> tuple[dict[str, dict], list[dict]]:
        with self.lock:
            return ({src: dict(item) for src, item in self.items.items()},
                    list(self.history))


runner = Runner()


def folder_of(name: str) -> Path | None:
    return {"inbox": convert.INBOX, "outbox": convert.OUTBOX,
            "done": convert.DONE}.get(name)


def inside_our_folders(path: Path) -> bool:
    path = path.resolve()
    return any(path.is_relative_to(f.resolve())
               for f in (convert.INBOX, convert.OUTBOX, convert.DONE))


def build_state() -> dict:
    jobs, warnings = convert.scan()
    run, history = runner.snapshot()
    now = time.time()

    inbox = []
    for job in jobs:
        item = run.get(str(job.src), {})
        status = item.get("status") or ("pending" if job.engine else "unsupported")
        inbox.append({
            "src": str(job.src),
            "name": job.src.name,
            "target": job.target,
            "status": status,
            "message": item.get("message") or job.note,
            "elapsed": round(now - item["started"]) if status == "running" else None,
        })

    done = [{**entry, "outputs": [{"path": p, "label": convert.show(Path(p))}
                                  for p in entry["outputs"]]}
            for entry in reversed(history)]

    return {
        "routes": {t: sorted(exts) for t, exts in ROUTES.items()},
        "inbox": inbox,
        "done": done,
        "running": runner.running,
        "warnings": warnings,
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "fileconv"

    def log_message(self, format, *args) -> None:   # 網頁每秒輪詢，不要洗版
        pass

    # ── 安全檢查 ──
    # 伺服器只綁 127.0.0.1，但你瀏覽的其他網站仍然可能對 localhost 發請求。
    # Host 檢查擋掉 DNS rebinding；POST 要求自訂 header，瀏覽器跨網域送
    # 自訂 header 必須先過 CORS preflight，我們不回應，所以一律被擋。
    def _trusted(self, need_header: bool) -> bool:
        port = self.server.server_address[1]
        allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if self.headers.get("Host") not in allowed:
            return False
        origin = self.headers.get("Origin")
        if origin and origin.removeprefix("http://") not in allowed:
            return False
        return not need_header or self.headers.get("X-Fileconv") == "1"

    def _send(self, status: int, body: bytes, ctype: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data, status: int = HTTPStatus.OK) -> None:
        self._send(status, json.dumps(data, ensure_ascii=False).encode(),
                   "application/json; charset=utf-8")

    def _error(self, status: int, message: str) -> None:
        self._json({"error": message}, status)

    def _body_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return {}

    # ── GET ──
    def do_GET(self) -> None:
        if not self._trusted(need_header=False):
            return self._error(HTTPStatus.FORBIDDEN, "拒絕存取")
        path = urlparse(self.path).path
        if path == "/":
            return self._send(HTTPStatus.OK, PAGE.read_bytes(), "text/html; charset=utf-8")
        if path == "/api/state":
            return self._json(build_state())
        self._error(HTTPStatus.NOT_FOUND, "找不到")

    # ── POST ──
    def do_POST(self) -> None:
        if not self._trusted(need_header=True):
            return self._error(HTTPStatus.FORBIDDEN, "拒絕存取")
        url = urlparse(self.path)
        if url.path == "/api/upload":
            return self._upload(parse_qs(url.query))
        if url.path == "/api/convert":
            count = runner.start()
            if not count:
                return self._error(HTTPStatus.CONFLICT,
                                   "正在轉換中" if runner.running else "沒有可以轉換的檔案")
            return self._json({"started": count})
        if url.path == "/api/cancel":
            runner.cancel = True
            return self._json({"ok": True})
        if url.path == "/api/reveal":
            target = Path(self._body_json().get("path", ""))
            if not target.exists() or not inside_our_folders(target):
                return self._error(HTTPStatus.BAD_REQUEST, "只能開啟轉檔資料夾裡的檔案")
            subprocess.run(["open", "-R", str(target)], check=False)
            return self._json({"ok": True})
        if url.path == "/api/open":
            folder = folder_of(self._body_json().get("folder", ""))
            if folder is None:
                return self._error(HTTPStatus.BAD_REQUEST, "未知的資料夾")
            folder.mkdir(parents=True, exist_ok=True)
            subprocess.run(["open", str(folder)], check=False)
            return self._json({"ok": True})
        self._error(HTTPStatus.NOT_FOUND, "找不到")

    def _upload(self, query: dict[str, list[str]]) -> None:
        target = (query.get("target") or [""])[0]
        name = Path((query.get("name") or [""])[0]).name   # 去掉任何路徑，只留檔名
        length = int(self.headers.get("Content-Length") or -1)

        if target not in ROUTES:
            return self._error(HTTPStatus.BAD_REQUEST, "未知的目標格式")
        if not name or name.startswith((".", "~$")):
            return self._error(HTTPStatus.BAD_REQUEST, "檔名不合法")
        if Path(name).suffix.lower() not in ROUTES[target]:
            return self._error(HTTPStatus.BAD_REQUEST,
                               f"「{name}」不能轉成 {target}")
        if length < 0:
            return self._error(HTTPStatus.LENGTH_REQUIRED, "缺少檔案大小")

        folder = convert.INBOX / target
        folder.mkdir(parents=True, exist_ok=True)
        # 先寫到隱藏的暫存檔，傳完才改名：scan() 會略過隱藏檔，
        # 所以不會有人拿到傳到一半的檔案去轉。
        partial = folder / f".uploading-{uuid.uuid4().hex}"
        try:
            with open(partial, "wb") as f:
                remaining = length
                while remaining:
                    chunk = self.rfile.read(min(UPLOAD_CHUNK, remaining))
                    if not chunk:
                        raise ConnectionError("上傳中斷")
                    f.write(chunk)
                    remaining -= len(chunk)
            final = unique_path(folder / name)
            partial.rename(final)
        except BaseException:
            partial.unlink(missing_ok=True)
            raise
        self._json({"saved": convert.show(final)})


def make_server(port: int) -> ThreadingHTTPServer:
    for candidate in range(port, port + 20):
        try:
            return ThreadingHTTPServer((HOST, candidate), Handler)
        except OSError:
            continue
    sys.exit(f"錯誤: {port}–{port + 19} 的埠號都被占用了")


def main() -> int:
    p = argparse.ArgumentParser(description="轉檔工具的本機網頁介面")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--no-browser", action="store_true", help="不要自動打開瀏覽器")
    args = p.parse_args()

    convert.ensure_folders()
    server = make_server(args.port)
    url = f"http://{HOST}:{server.server_address[1]}/"
    print(f"轉檔工具已啟動: {url}")
    print("關閉這個視窗或按 Ctrl+C 結束")
    if not args.no_browser:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        if runner.running:
            print("\n等目前這個檔案轉完就結束（再按一次 Ctrl+C 強制結束）…")
            runner.cancel = True
            runner.thread.join()
    finally:
        server.server_close()
    print("已結束")
    return 0


if __name__ == "__main__":
    sys.exit(main())
