# dropconvert（轉檔工具）

Mac 上的資料夾式轉檔工具：把檔案拖進視窗（或丟進資料夾），按一下就轉好。
支援日常最常用的三大類：

- **文件**：Word／Excel／PowerPoint → PDF、Markdown ↔ Word、文件 → Markdown
- **圖片**：JPG ↔ PNG ↔ PDF（也吃 HEIC、TIFF、WebP），或把多張圖片／PDF **合併成一份 PDF**
- **影片**：WMV／MOV → MP4（能無損就不重壓，否則用硬體編碼）

全部在 Mac 本機執行，檔案不會上傳到任何地方。Office 文件用你已經安裝的 Microsoft Office 轉，
排版和你在 Office 裡看到的完全一樣，新細明體、標楷體都會正確嵌入 PDF。

## 安裝

打開「終端機」（Launchpad 搜尋「終端機」），貼上這一行後按 Enter：

```bash
/bin/zsh -c "$(curl -fsSL https://raw.githubusercontent.com/Jimmy0219/dropconvert/main/install.sh)"
```

安裝程式會自動補齊需要的工具，第一次大約要 5–15 分鐘（視網路速度），過程中可能會：

- 跳出「Xcode Command Line Tools」安裝視窗：按「安裝」，裝好後**再貼一次上面那行**
- 要求輸入 Mac 的登入密碼：安裝 Homebrew 時需要（輸入時畫面不會顯示字元，是正常的）

裝好後會自動打開，之後在 **Launchpad 或 Spotlight 搜尋「轉檔工具」** 就能開啟。

**第一次使用時 macOS 會詢問兩種權限，都請按「允許」：**

- 「轉檔工具」想要取用「下載項目」資料夾中的檔案：`待轉檔`、`已轉檔` 都放在這裡
- 「轉檔工具」想要控制「Microsoft Word」（Excel、PowerPoint 各問一次）：轉 PDF 用

需要：macOS 12 以上、Apple 晶片或 Intel 都可以；Office 轉 PDF 需要 Microsoft Office。

### 更新與解除安裝

- **更新**：再貼一次上面的安裝指令
- **解除安裝**：

  ```bash
  /bin/zsh -c "$(curl -fsSL https://raw.githubusercontent.com/Jimmy0219/dropconvert/main/install.sh)" -- --uninstall
  ```

  會移除 App 和程式本身；`~/Downloads` 裡的 `待轉檔`、`已轉檔`、`已處理` 和你的檔案都會保留。

想先看看安裝程式做了什麼，可以直接讀 [install.sh](install.sh)。

## 從原始碼建置（開發者）

一般使用者用上面的安裝指令就好。要自己改程式的話：

```bash
brew install ffmpeg pandoc poppler uv
git clone https://github.com/Jimmy0219/dropconvert.git
cd dropconvert
./make_app.sh             # 產生 轉檔工具.app（放在專案資料夾）
```

- **Microsoft Word／Excel／PowerPoint**：Office 轉 PDF 需要，放在 `/Applications`
- **Xcode Command Line Tools**：`make_app.sh` 用 `clang` 編譯 App 的啟動器
- 轉檔核心只用 Python 標準庫；App 視窗用 [pywebview](https://pywebview.flowrl.com/)，
  由 `uv sync` 裝進專案的 `.venv`（`make_app.sh` 會自動執行）
- 文件轉 Markdown 用 [markitdown](https://github.com/microsoft/markitdown)，透過 `uvx`
  自動下載，**第一次使用要等幾分鐘**，之後就用快取

## 使用方式

有兩種用法，操作的是同一組資料夾，可以混著用。

### 轉檔工具.app

1. 把檔案拖到想要的格式格子裡（或點一下格子選檔）
2. 按「開始轉換」，每個檔案的進度會即時更新
3. 轉好的檔案出現在「轉換完成」，點檔名就會在 Finder 中顯示

轉換中可以按「停止」，目前這個檔案轉完就會停，剩下的留在原處，下次再轉。
轉換中關閉視窗會先詢問；確定的話，會等目前的檔案轉完才真正結束。

幾個細節：

- 拖進視窗的檔案會**複製**到 `待轉檔/`，你原本的檔案不會被移動
- 直接把檔案丟進 `待轉檔/` 的子資料夾，視窗裡也會自動顯示
- 執行紀錄寫在 `~/Library/Logs/轉檔工具.log`，出問題時可以看這裡
- 自己用 `make_app.sh` 建置的話：**專案資料夾搬家或改名後，要重新執行 `./make_app.sh`**。
  App 只是啟動器，程式碼仍在專案資料夾裡執行；沒重新產生的話，打開 App 會跳出提示

### 指令

```bash
./convert.py              # 轉換「待轉檔」裡的所有檔案
./convert.py --dry-run    # 只列出會怎麼處理，不轉檔、不搬檔、不建資料夾
```

### 資料夾

第一次執行會在 `~/Downloads` 建好資料夾。**子資料夾的名稱就是你要的目標格式**，
想轉成什麼就丟進哪個資料夾：

```
~/Downloads/
├── 待轉檔/          ← 你放檔案的地方
│   ├── pdf/         報告.docx、報表.xlsx、簡報.pptx、照片.jpg
│   ├── md/          報告.docx、講義.pdf
│   ├── docx/        筆記.md
│   ├── jpg/         截圖.png、掃描.pdf
│   ├── png/         照片.jpg、iPhone.heic
│   ├── mp4/         錄影.mov、舊影片.wmv
│   └── 合併pdf/
│       └── 出差收據/   1.jpg、2.jpg、3.png   ← 一個子資料夾合併成一份
├── 已轉檔/          ← 轉好的檔案，一樣依格式分資料夾
│   ├── pdf/         報告.pdf、報表.pdf …
│   └── 合併pdf/     出差收據.pdf
└── 已處理/          ← 轉換成功後，原始檔移到這裡
    └── pdf/         報告.docx …
```

直接放在 `待轉檔/` 根目錄的影片也會轉成 MP4（沿用 wmv2mp4 原本的習慣）。
資料夾位置在 [convert.py](convert.py) 開頭的 `BASE`、`INBOX`、`OUTBOX`、`DONE`，要換地方改那裡就好。

## 支援的轉換

| 丟進 | 可接受的檔案 | 轉換引擎 |
| --- | --- | --- |
| `pdf/` | `.doc` `.docx` `.rtf` | Microsoft Word |
| | `.xls` `.xlsx` | Microsoft Excel（所有工作表都會輸出） |
| | `.ppt` `.pptx` | Microsoft PowerPoint |
| | `.jpg` `.jpeg` `.png` `.heic` `.tif` `.tiff` `.webp` | `sips`（macOS 內建） |
| `md/` | `.docx` `.pptx` `.xlsx` `.xls` `.pdf` `.html` `.htm` | markitdown |
| `docx/` | `.md` `.markdown` | pandoc |
| `jpg/` `png/` | 其他圖片格式 | `sips` |
| | `.pdf` | poppler `pdftoppm`（200 dpi，每頁一張） |
| `mp4/` | `.wmv` `.asf` `.mov` `.qt` | ffmpeg（見下方〈影片轉檔細節〉） |
| `合併pdf/<名稱>/` | 圖片（同上）與 `.pdf`，可以混著放 | macOS 內建的 CoreGraphics／PDFKit |

多頁 PDF 轉圖片時，會放進同名資料夾：`已轉檔/jpg/講義/講義-1.jpg`、`講義-2.jpg`…；
單頁 PDF 則直接輸出 `已轉檔/jpg/講義.jpg`。

### 合併成一份 PDF

- **在 App 裡**：把要合併的檔案**一次**拖進「合併成一份 PDF」格子。
  預設檔名是「第一個檔名–最後一個檔名」（例如 `收據1–收據10.pdf`），轉好後可以自己改名
- **用資料夾**：在 `待轉檔/合併pdf/` 底下開一個子資料夾，資料夾名稱就是輸出的檔名；
  直接放在 `合併pdf/` 這一層的檔案不會處理，因為不知道要跟誰合併
- **頁面順序依檔名的自然順序**：`2.png` 排在 `10.png` 前面。想調整順序，改檔名就好
- **畫質不變**：JPEG 原樣嵌入不重新壓縮，PNG／HEIC 無損保存，像素完整保留
- 圖片頁寬統一為 A4 寬、高度依圖片比例，列印時不會出現超大頁面
- 手機照片會依 EXIF 自動轉正，不會橫躺
- PDF 整頁搬過來，文字、向量圖和連結都保留；有密碼保護的 PDF 無法合併
- 子資料夾裡混了其他檔案（例如 `.txt`）時，整批會略過並說明原因，不會只合併一部分

## 行為細節

- **成功**：輸出到 `已轉檔/<格式>/`，原始檔移到 `已處理/<格式>/`
- **失敗**或**不支援的格式**：原始檔留在原處，下次執行會再試；訊息會說明原因與可接受的格式
- **撞名**：輸出或已處理資料夾裡有同名檔案時，自動改成 `報告 (2).pdf`，不會覆蓋
- **略過**：隱藏檔（`.DS_Store`）、Office 鎖定檔（`~$` 開頭）、不認得的子資料夾
- **中斷**：`Ctrl+C` 會連同外部程式一起停止並清掉半成品，回傳 130
- **退出碼**：全部成功回傳 0，有任何檔案失敗回傳 1

## Office 轉 PDF 的做法

透過 AppleScript 叫 Office 自己「另存 PDF」，所以轉出來跟在 Office 裡按「另存新檔」
完全一樣。轉換時 Office 會在背景開啟，你可能會看到視窗閃一下。

幾個實作上的保護：

- **不會動到你開著的文件**：用完整路徑精準找到工具自己開的那一份，只關閉那一份
- **不會把 Office 留在背景**：這次執行才被叫起來的 Office，全部轉完會自動結束；
  執行前就開著的 Office 則維持原狀
- **不會跳出授權視窗**：Office 在沙盒裡，直接寫到 `~/Downloads` 可能要你手動授權，
  所以先匯出到 `/private/tmp` 再由工具搬過去
- **不會卡死**：文件有密碼等情況 Office 會跳對話框等人回應，超過 5 分鐘就判定失敗

## 已知限制

- Office 轉 PDF 一次處理一份，每份約數秒；大量檔案時會比較久
- 丟進 `pdf/` 的圖片是一張圖一個 PDF；要合併請用「合併成一份 PDF」
- Markdown 轉 Word 用 pandoc 預設樣式，不會套用你自己的 Word 範本
- Markdown 裡用相對路徑引用的圖片會正確嵌入，但圖片檔本身不會跟著移到 `已處理/`

## 專案結構

| 檔案 | 用途 |
| --- | --- |
| [app.py](app.py) | App 主程式：開原生視窗（pywebview），在背景啟動 `ui.py` 的本機伺服器 |
| [ui.html](ui.html) | 視窗裡的介面，CSS/JS 都在裡面，不從網路載入任何東西 |
| [ui.py](ui.py) | 視窗和核心之間的本機 API（只綁 `127.0.0.1`），在背景執行緒呼叫 `run_job()`；也可以單獨執行 `./ui.py` 用瀏覽器開 |
| [convert.py](convert.py) | 核心：`scan()` 掃描資料夾、`run_job()` 轉一個檔案並搬檔；也是指令版的入口 |
| [engines.py](engines.py) | 各種轉換引擎，以及「目標格式 → 來源格式 → 引擎」的對照表 `ROUTES` |
| [wmv2mp4.py](wmv2mp4.py) | 影片轉換邏輯；也可以單獨當 CLI 使用（見下方） |
| [install.sh](install.sh) | 給一般使用者的安裝／更新／解除安裝腳本 |
| [make_app.sh](make_app.sh) | 產生 `轉檔工具.app`：安裝相依套件、產生圖示、編譯啟動器 |
| [launcher.c](launcher.c) | App 的執行檔：把 Python 載進自己的程序執行，系統才會把它認成「轉檔工具」而不是 python |
| [merge_pdf.py](merge_pdf.py) | 把圖片與 PDF 合併成一份 PDF（CoreGraphics／PDFKit，由 `engines.py` 呼叫） |
| [make_icon.py](make_icon.py)、[icon.svg](icon.svg) | App 圖示的原稿，以及轉成 `.icns` 的腳本 |

要新增一種轉換，在 `engines.py` 寫一個 `engine(src, dst) -> list[Path]` 函式，
再加進 `ROUTES` 就好。

## 影片轉檔細節

`convert.py` 處理影片時沿用 `wmv2mp4.py` 的邏輯與預設值。`wmv2mp4.py` 也可以單獨使用，
提供更多影片參數：

```bash
./wmv2mp4.py                        # 不帶參數：轉 ~/Downloads/待轉檔 根目錄的影片，輸出在同目錄
./wmv2mp4.py clip.mov               # 單檔
./wmv2mp4.py videos/ -r -o out/     # 資料夾遞迴、指定輸出目錄
./wmv2mp4.py a.wmv -q 75            # 提高品質
./wmv2mp4.py a.wmv -b 8M            # 直接指定位元率
./wmv2mp4.py a.mov --reencode --hevc  # 強制重壓成 HEVC
./wmv2mp4.py a.wmv --cpu            # 改用 CPU 的 libx264
./wmv2mp4.py a.wmv --force          # 覆寫已存在的輸出
```

| 參數 | 說明 |
| --- | --- |
| `input` | 來源檔案或資料夾，可省略（省略時用 `~/Downloads/待轉檔`） |
| `-o, --output-dir` | 輸出目錄（預設與來源同目錄） |
| `-q, --quality` | 品質 1–100，預設 60 |
| `-b, --bitrate` | 指定視訊位元率如 `8M`，設了就取代 `--quality` |
| `--hevc` | 重新編碼時用 H.265/HEVC，同畫質檔案更小 |
| `--reencode` | 即使來源相容也強制重新編碼視訊 |
| `--cpu` | 強制 libx264/libx265，不用硬體編碼 |
| `--preset` | libx26x preset，僅 `--cpu` 時有效（預設 medium） |
| `--audio-bitrate` | 音訊位元率（預設 192k，僅在需要重壓音訊時使用） |
| `-r, --recursive` | 資料夾模式遞迴掃描 |
| `-f, --force` | 覆寫已存在的輸出檔（預設跳過） |

### 什麼時候會重壓，什麼時候不會

腳本會先用 ffprobe 讀出來源的視訊/音訊編碼，再分開決定兩條軌各自要 copy 還是重壓：

| 來源 | 視訊 | 音訊 | 結果 |
| --- | --- | --- | --- |
| MOV（H.264 + AAC，iPhone、螢幕錄影常見） | copy | copy | 無損重封裝，秒轉 |
| MOV（H.264 + PCM） | copy | 轉 AAC | 畫面零損失 |
| MOV（ProRes、DNxHD 等） | 重壓 | 轉 AAC | MP4 容器裝不下 ProRes |
| WMV/ASF（WMV3/VC-1 + WMA） | 重壓 | 轉 AAC | 兩種編碼 MP4 都不支援 |

**WMV 一定要重壓**：WMV3/VC-1 視訊與 WMA 音訊 MP4 容器都不收，沒得選。長片會跑上
幾分鐘到幾十分鐘。預設用 `h264_videotoolbox`（M1 的硬體編碼器），比 CPU 的 `libx264`
快數倍、發熱和記憶體壓力都低很多，在 8GB 機器上差異特別明顯。

想強制重壓（例如要縮小檔案）就加 `--reencode`。它只強制重壓**視訊**——音訊本來就是
AAC 的話仍然直接沿用，不會再壓一次白白掉品質。

### 關於畫質

轉檔不可能無中生有把畫質變好，能做的是**盡量不要損失**。腳本做了這幾件事：

1. **能不重壓就不重壓**。MOV 走 `-c copy` 時輸出的視訊位元流與來源逐位元相同
   （實測來源與輸出的視訊/音訊 MD5 完全一致），這是唯一真正零損失的路徑。
2. **重壓時保留色彩描述**。把來源的 `color_primaries`／`color_trc`／`colorspace`／
   `color_range` 原樣寫進輸出，播放器才不會猜錯，避免顏色偏掉、發灰。
3. **`--hevc` 保留 10-bit**。來源是 10-bit 時輸出 `yuv420p10le`，漸層不會出現色帶；
   並自動加上 `hvc1` tag，否則 QuickTime 會拒播。
4. **HDR 提醒**。來源是 HDR（PQ / HLG）又要壓成 8-bit H.264 時會警告，建議改用 `--hevc`。
5. **保留 metadata**（`-map_metadata 0`），拍攝時間等資訊不會掉。

如果來源本身就糊（低位元率、低解析度），任何轉檔工具都救不回來——放大或銳化只會
讓它看起來更不自然。

### 品質參數的刻度差異

`-q` 統一用 1–100（越大越好），但底層兩個編碼器的刻度不同，腳本會自動換算：

- **VideoToolbox**：直接對應 `-q:v 1-100`
- **libx264/libx265**：換算成 CRF（越小越好），範圍 40–14

| `-q` | 1 | 30 | 60 | 75 | 90 | 100 |
| --- | --- | --- | --- | --- | --- | --- |
| CRF | 40 | 32 | 25 | 21 | 17 | 14 |

同一個 `-q` 值在兩個編碼器下產生的檔案大小**不會相同**，要精確控制請改用 `-b/--bitrate`。

### 輸出設定

- `-movflags +faststart`：moov atom 移到檔頭，網頁串流可邊下載邊播
- `-pix_fmt yuv420p`：確保 QuickTime 與 iOS 能正常播放（HEVC + 10-bit 來源除外）
- `-map 0:v:0 -map 0:a?`：只帶第一條視訊與所有音訊軌，避免 MP4 裝不下的雜項軌造成失敗

### wmv2mp4.py 單獨使用時的行為

- 輸出檔已存在時**預設跳過**，要覆寫請加 `--force`
- 來源無法解析（損毀、非影片）會標記失敗並繼續處理下一個，不中斷整批
- 轉換失敗時會刪掉半成品，不留下無法播放的殘檔
- `Ctrl+C` 中斷回傳 130

## 授權

[MIT](LICENSE)。本工具會呼叫你電腦上另外安裝的 ffmpeg、pandoc、poppler、markitdown
與 Microsoft Office，它們各自依照自己的授權條款使用，並沒有包含在這個專案裡。
