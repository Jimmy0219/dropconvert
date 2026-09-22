/*
 * 轉檔工具.app 的執行檔（由 make_app.sh 編譯）。
 *
 * 為什麼不用 shell script 直接 exec python？macOS 是看「執行檔在哪裡」來
 * 認定這是哪個 App：執行檔若是 .venv 裡的 python，Dock、⌘Tab、權限詢問
 * 視窗都會顯示「python」。所以改由這個位在 .app 裡的小程式把 Python
 * 載進自己的程序執行，系統就會把它當成「轉檔工具」。
 *
 * PROJECT_DIR 由 make_app.sh 產生的 config.h 提供。
 */
#include <Python.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

#include "config.h"

#define VENV_PYTHON PROJECT_DIR "/.venv/bin/python"
#define APP_SCRIPT  PROJECT_DIR "/app.py"

static void alert(const char *message) {
    char cmd[2048];
    snprintf(cmd, sizeof cmd,
             "osascript -e 'display alert \"轉檔工具無法啟動\" message \"%s\" as critical'",
             message);
    system(cmd);
}

static int fail(PyConfig *config, PyStatus status) {
    PyConfig_Clear(config);
    alert(status.err_msg ? status.err_msg : "Python 初始化失敗");
    Py_ExitStatusException(status);
    return 1;
}

int main(void) {
    if (access(VENV_PYTHON, X_OK) != 0 || access(APP_SCRIPT, R_OK) != 0) {
        alert("找不到專案資料夾或 Python 環境：\n" PROJECT_DIR
              "\n\n如果專案搬家或改名了，請在新的專案資料夾執行 ./make_app.sh 重新產生 App。");
        return 1;
    }

    // 從 Finder 開啟的 App 只有很精簡的 PATH，補上 Homebrew 與 uv 的位置，
    // 否則會找不到 ffmpeg、pandoc、pdftoppm、uvx。
    const char *home = getenv("HOME");
    const char *old_path = getenv("PATH");
    char path[4096];
    snprintf(path, sizeof path, "/opt/homebrew/bin:/usr/local/bin:%s/.local/bin:%s",
             home ? home : "", old_path ? old_path : "/usr/bin:/bin:/usr/sbin:/sbin");
    setenv("PATH", path, 1);

    // GUI App 沒有終端機，輸出寫進 ~/Library/Logs/轉檔工具.log 方便除錯
    if (home) {
        char log[1024];
        snprintf(log, sizeof log, "%s/Library/Logs/轉檔工具.log", home);
        freopen(log, "a", stdout);
        freopen(log, "a", stderr);
        setvbuf(stdout, NULL, _IOLBF, 0);
    }

    chdir(PROJECT_DIR);

    PyConfig config;
    PyConfig_InitPythonConfig(&config);
    config.parse_argv = 0;
    // 把 program_name 設成 venv 的 python：Python 會據此找到 pyvenv.cfg，
    // 載入 .venv 裡安裝的 pywebview。
    PyStatus status = PyConfig_SetBytesString(&config, &config.program_name, VENV_PYTHON);
    if (PyStatus_Exception(status)) return fail(&config, status);
    status = PyConfig_SetBytesString(&config, &config.run_filename, APP_SCRIPT);
    if (PyStatus_Exception(status)) return fail(&config, status);
    char *argv[] = {APP_SCRIPT};
    status = PyConfig_SetBytesArgv(&config, 1, argv);
    if (PyStatus_Exception(status)) return fail(&config, status);

    status = Py_InitializeFromConfig(&config);
    PyConfig_Clear(&config);
    if (PyStatus_Exception(status)) return fail(&config, status);
    return Py_RunMain();
}
