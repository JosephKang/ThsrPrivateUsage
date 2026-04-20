# THSR-Ticket 功能規格文件

## 專案概述

CLI 工具，自動化台灣高鐵（THSR）線上訂票流程。透過 HTTP 表單抓取與提交取代手動操作網頁 UI。

- **執行環境**：Python 3.12、WSL2（主要開發環境）
- **互動入口**：`thsr_ticket/main.py` → `BookingFlow.run()`
- **自動入口**：`scripts/book_auto.py` → `BookingFlow.run(args)` （無互動）
- **依賴管理**：`requirements.txt`，建議使用 `.venv`

---

## 執行方式

```bash
# 完全互動模式
.venv/bin/python -m thsr_ticket.main

# 帶參數（跳過對應互動提示）
# -i 提供 2 筆 → 自動成人票數 = 2，無需 -a
.venv/bin/python -m thsr_ticket.main \
  -f 2 -t 12 -d 2026-05-14 -T 10 \
  -i "A123456789|B987654321" \
  -m n \
  -p 0912345678

# 明確指定票數（-a 優先於 id 筆數）
.venv/bin/python -m thsr_ticket.main \
  -f 2 -t 12 -d 2026-05-14 -T 10 -a 1 \
  -i "A123456789" -m y -p 0912345678

# 查詢輔助
.venv/bin/python -m thsr_ticket.main --list-station
.venv/bin/python -m thsr_ticket.main --list-time-table

# 自動訂票（無互動，讀 cfg/SOB.md 或 cfg/EOB.md）
python scripts/book_auto.py --date 2026-04-21              # SOB，依星期自動選時段
python scripts/book_auto.py --date 2026-04-21 --profile EOB
python scripts/book_auto.py --date 2026-04-21 --no-discount  # 不限優惠班次
```

---

## CLI 參數（`main.py`）

| 參數 | 說明 | 未提供時 |
|---|---|---|
| `-f / --from-station` | 起程站編號（1=南港 … 12=左營） | 互動選擇 |
| `-t / --to-station` | 到達站編號 | 互動選擇 |
| `-d / --date` | 出發日期（`YYYY-MM-DD` 或 `YYYY/MM/DD`） | 互動輸入 |
| `-T / --time` | 時間編號（1-based，見 `--list-time-table`） | 互動選擇 |
| `-a / --adult` | 成人票數（0~10）；省略時由 `-i` 筆數推算 | 互動輸入 |
| `-i / --id` | 身分證字號，多筆以 `\|` 分隔（見下方說明） | 互動輸入 |
| `-m / --membership` | 使用高鐵會員：`y` 或 `n` | 互動詢問 |
| `-p / --phone` | 手機號碼（選填） | 互動輸入 |
| `--list-station` | 列出車站編號後離開 | — |
| `--list-time-table` | 列出時間編號後離開 | — |

### `--id` 多筆規則

```
-i "A123456789|B987654321|C111222333"
      │            │            └─ 早鳥乘客 3（第 3 位乘客）
      │            └─────────────── 早鳥乘客 2（第 2 位乘客）
      └──────────────────────────── 訂票人身分證 / 會員號碼 / 早鳥乘客 1 預設
```

| 規則 | 說明 |
|---|---|
| **ID 筆數 = 總訂票人數** | 省略 `-a` 時，自動將成人票數設為 ID 筆數 |
| **`-a` 優先於 ID 筆數** | 同時提供 `-a N` 時，以 `-a` 為準 |
| **第一筆 = 會員號碼** | 第一筆 ID 同時作為 `memberShipNumber`（啟用會員時） |
| **早鳥乘客 1** | 顯示預設值（= 第一筆 ID），按 Enter 確認或輸入覆蓋 |
| **早鳥乘客 2+** | 自動帶入對應 ID；筆數不足則改為互動輸入（不可空白） |
| **Shell 引號** | `\|` 是 Shell 管線符號，**必須加引號**：`-i "A\|B"` |

---

## 整體流程

```
main() → parse args
    │
    ▼
BookingFlow.run(args)
    │
    ├─ 1. 顯示歷史記錄（TinyDB），使用者可選擇套用
    │
    ├─ 2. FirstPageFlow.run(args)
    │       ├─ 選擇起程站（args.from_station 或互動）
    │       ├─ 選擇到達站（args.to_station 或互動）
    │       ├─ 選擇出發日期（args.date 或互動）
    │       ├─ 選擇出發時間（args.time 或互動）
    │       ├─ 選擇成人票數（args.adult > len(args.id) > 互動）
    │       ├─ 自動辨識驗證碼（含備援機制）
    │       └─ POST → THSR 訂票頁
    │
    ├─ 3. ConfirmTrainFlow.run(args)
    │       ├─ 解析可用班次（含早鳥 / 學生優惠標籤）
    │       ├─ 選擇班次：
    │       │     args.require_discount=True → 自動選第一班 8折/65折（無則 NoDiscountError）
    │       │     否則 → 互動選擇
    │       └─ POST → 班次確認頁
    │
    ├─ 4. ConfirmTicketFlow.run(args)
    │       ├─ 身分證字號（args.id[0] 或歷史記錄或互動）
    │       ├─ 高鐵會員（args.membership 或互動 y/n）
    │       ├─ 手機號碼（args.phone 或歷史記錄或互動）
    │       ├─ 早鳥乘客身份證（args.id[1..] 或互動）
    │       └─ POST → 最終確認頁
    │
    └─ 5. 顯示訂位結果，儲存 Record 至 TinyDB
```

---

## 功能說明

### 1. 歷史記錄（`model/db.py`）

- 使用 TinyDB 將訂位資訊（起/迄站、時間、身份證、手機）儲存為 `Record`
- 下次啟動時顯示歷史，使用者可選擇套用以跳過重複輸入
- CLI 參數優先順序：CLI arg > 歷史記錄 > 互動輸入

---

### 2. 第一頁：出發選項（`controller/first_page_flow.py`）

#### 站點選擇
- 12 站：南港、台北、板橋、桃園、新竹、苗栗、台中、彰化、雲林、嘉義、台南、左營
- 站代碼定義於 `configs/web/`

#### 日期 / 時間選擇
- 訂票窗口：今日起 27 天內（定義於 `configs/common.py`）
- 時段：43 個選項（`1201A` ～ `1130P`，AM/PM 格式）

#### 票種
| 欄位 | 票種 | 表單值格式 |
|---|---|---|
| `ticketPanel:rows:0:ticketAmount` | 大人 | `{n}F` |
| `ticketPanel:rows:1:ticketAmount` | 孩童（6~11歲） | `{n}H` |
| `ticketPanel:rows:2:ticketAmount` | 愛心（台灣限定） | `{n}W` |
| `ticketPanel:rows:3:ticketAmount` | 敬老（台灣限定） | `{n}E` |
| `ticketPanel:rows:4:ticketAmount` | 大學生（台灣限定） | `{n}P` |

#### 驗證碼自動辨識
詳見 [`docs/captcha_spec.md`](captcha_spec.md)。

流程摘要：
1. `_preprocess_captcha()` — 灰階 → median blur → Otsu 二值化 → 形態學開運算 → 小物件移除
2. `_ddddocr_recognize()` — OCR 辨識，結果必須為 4 碼
3. **互動模式**：成功 → 顯示預測值，按 Enter 確認或輸入修正值；失敗 → 終端以 Unicode Braille 渲染圖片，手動輸入
4. **自動模式**（`args.auto_captcha=True`）：直接使用 OCR 結果，無確認提示；結果為空 → 拋出 `CaptchaError`
5. WSL 環境：同時將原圖與清理圖（4× 放大）儲存至 Windows Downloads

---

### 3. 第二頁：班次確認（`controller/confirm_train_flow.py`）

- 解析所有可選班次，每筆顯示：車次 / 出發 ～ 抵達時間 / 行車時間 / 優惠標籤
- 優惠標籤來源（`view_model/avail_trains.py`）：
  - 早鳥優惠：`<p class="early-bird">`
  - 學生優惠：`<p class="student">`
- 班次選擇模式：

| 模式 | 條件 | 行為 |
|---|---|---|
| 互動模式 | `args.require_discount` 未設 | 使用者輸入編號選擇 |
| 自動模式 | `args.require_discount=True` | 自動選第一班含 `8折` 或 `65折` 的班次；無則拋出 `NoDiscountError` |

---

### 4. 第三頁：乘客確認（`controller/confirm_ticket_flow.py`）

#### 身分證字號
- 優先順序：`args.id.split('|')[0]` > 歷史 Record > 互動輸入
- 同時作為高鐵會員號碼（啟用會員時）

#### 高鐵會員
`_select_member_radio(page, personal_id, args)`

| 來源 | 條件 |
|---|---|
| `args.membership == 'y'` | 自動使用會員 |
| `args.membership == 'n'` | 自動不使用 |
| 未提供 | 互動詢問 `y/n` |

| 選擇 | HTML 選取器 | 額外 POST 欄位 |
|---|---|---|
| 非會員（預設） | `#memberSystemRadio3` | 無 |
| 高鐵會員 | `#memberSystemRadio1` | `memberShipNumber=args.id[0]`, `memberSystemShipCheckBox=on` |

- radio value 從 HTML runtime 解析（非硬編碼）
- 會員號碼固定使用 `args.id[0]`（第一筆 ID）

#### 手機號碼
- 優先使用 `args.phone`，其次歷史 Record，最後互動輸入
- 允許空字串（選填）

#### 早鳥乘客身份證
`_process_early_bird(page, personal_id, args)`

- 偵測 `.superEarlyBird` 元素個數（= 需填身份證的乘客數）
- 早鳥票種（`passengerDataTypeName`）由 HTML hidden input 決定
- 乘客 0：優先 `args.id[0]`（仍顯示確認提示，可覆蓋）
- 乘客 1+：優先 `args.id[i]`，不足則互動輸入（不可空白）
- 每位乘客提交欄位：

| 欄位後綴 | 說明 |
|---|---|
| `passengerDataLastName` | 姓（留空） |
| `passengerDataFirstName` | 名（留空） |
| `passengerDataTypeName` | 早鳥票種代碼 |
| `passengerDataIdNumber` | 身份證字號 |
| `passengerDataInputChoice` | `0`=身份證 / `1`=護照 |

---

### 5. 訂位結果（`view_model/booking_result.py`、`view/web/show_booking_result.py`）

顯示：
- 訂位代號（PNR）
- 繳費期限
- 總價
- 日期、起程站、目的站、出發時間、抵達時間、車次
- 座艙等級、座位號碼

---

## 自動訂票腳本（`scripts/book_auto.py`）

完全無互動的端到端訂票腳本，供排程或腳本化使用。詳細規格見 [`docs/book_auto.md`](book_auto.md)。

### 流程

```
book_auto.py --date DATE [--profile SOB|EOB] [--no-discount]
    │
    ├─ 解析 cfg/{profile}.md 預設參數
    ├─ 日期正規化（YYYY/MM/DD → YYYY-MM-DD）
    ├─ SOB profile：依星期覆寫 T（Mon–Thu=6/07:30，Fri=3/06:00）
    ├─ 建立 Namespace（auto_captcha=True, require_discount=True）
    │
    └─ BookingFlow(args=ns).run()
            ├─ CaptchaError  → exit(1)
            ├─ NoDiscountError → exit(2)
            └─ 成功           → exit(0)
```

### 結束代碼

| Exit Code | 原因 |
|---|---|
| `0` | 訂票成功 |
| `1` | 驗證碼辨識失敗、設定檔不存在、日期格式錯誤 |
| `2` | 無 8折／65折 優惠班次 |

### 例外類型（`thsr_ticket/exceptions.py`）

| 例外 | 拋出位置 | 條件 |
|---|---|---|
| `CaptchaError` | `_input_security_code()` | `auto_captcha=True` 且 OCR 結果為空 |
| `NoDiscountError` | `select_available_trains()` | `require_discount=True` 且無 8折/65折 班次 |

---

## HTTP 層（`remote/http_request.py`）

| 方法 | URL | 說明 |
|---|---|---|
| `request_booking_page()` | `BOOKING_PAGE_URL` | GET 訂票首頁，建立 session |
| `request_security_code_img()` | 動態解析自 HTML | GET 驗證碼圖片 |
| `submit_booking_form()` | `SUBMIT_FORM_URL?jsessionid={}` | POST 第一頁表單 |
| `submit_train()` | `CONFIRM_TRAIN_URL` | POST 班次選擇 |
| `submit_ticket()` | `CONFIRM_TICKET_URL` | POST 最終確認 |

- Session 以 `requests.Session` 維持（含 JSESSIONID cookie）
- 預設 retry 3 次

---

## 資料模型（`configs/web/param_schema.py`）

使用 Pydantic v1（`pydantic<2.0`）：

| 模型 | 對應表單 | 關鍵欄位 |
|---|---|---|
| `BookingModel` | 第一頁 | 起/迄站、日期、時間、票種、驗證碼 |
| `ConfirmTrainModel` | 第二頁 | `TrainQueryDataViewPanel:TrainGroup` |
| `ConfirmTicketModel` | 第三頁 | `dummyId`、`dummyPhone`、`memberSystemRadioGroup` |

早鳥 / 會員額外欄位以 plain `dict` 在 runtime 合併，不納入 Pydantic schema。

---

## 測試（`thsr_ticket/unittest/`）

| 測試檔 | 涵蓋範圍 |
|---|---|
| `model/test_booking_form.py` | `BookingForm` 欄位驗證、`get_params()` |
| `model/test_confirm_train.py` | `ConfirmTrain` 欄位驗證、`get_params()` |
| `model/test_confirm_ticket.py` | `ConfirmTicket` 欄位驗證、`get_params()` |
| `model/test_confirm_ticket_flow.py` | `_select_member_radio()`、`_process_early_bird()`、`ConfirmTicketFlow.run()` |
| `test_http_request.py` | 真實 HTTP 連線驗證（整合測試） |

---

## 依賴套件

| 套件 | 版本需求 | 用途 |
|---|---|---|
| `requests` | — | HTTP session |
| `beautifulsoup4` | >=4.8.2 | HTML 解析 |
| `pydantic` | <2.0 | 表單資料模型 |
| `tinydb` | >=3.15.2 | 歷史記錄 |
| `jsonschema` | >=3.0.1 | 表單 schema 驗證 |
| `pillow` | — | 驗證碼影像處理 |
| `opencv-python` | >=4.13 | 驗證碼前處理（blur / 二值化 / 形態學） |
| `scikit-image` | >=0.26 | 小物件移除 |
| `ddddocr` | >=1.6 | 驗證碼 OCR |
| `numpy` | >=2.4 | 影像陣列操作 |
