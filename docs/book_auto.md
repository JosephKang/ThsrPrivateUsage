# book_auto.py — 自動訂票腳本規格

## 概述

`scripts/book_auto.py` 是無互動自動訂票腳本，從 `cfg/SOB.md` 或 `cfg/EOB.md` 讀取預設參數，接受 `--date` 引數，根據星期幾自動調整出發時段，全程無需人工輸入。

---

## 執行方式

```bash
# 基本用法（SOB profile，今日日期）
python scripts/book_auto.py --date 2026-04-21

# 縮寫
python scripts/book_auto.py -d 2026-04-21

# EOB profile（Hsinchu → Nangang 晚間）
python scripts/book_auto.py --date 2026-04-21 --profile EOB

# 不限優惠班次（接受任何班次）
python scripts/book_auto.py --date 2026-04-21 --no-discount

# 日期格式兩者均可
python scripts/book_auto.py --date 2026/04/21
```

---

## CLI 參數

| 參數 | 說明 | 預設 |
|---|---|---|
| `--date / -d` | 出發日期（`YYYY-MM-DD` 或 `YYYY/MM/DD`） | 必填 |
| `--profile` | 訂票設定檔（`SOB` 或 `EOB`） | `SOB` |
| `--no-discount` | 關閉優惠班次過濾，接受任何班次 | 關閉 |

---

## 設定檔（Profile）

腳本從 `cfg/{profile}.md` 的 Markdown 表格讀取預設值：

| Profile | 設定檔 | 說明 |
|---|---|---|
| `SOB` | `cfg/SOB.md` | Start of Business：Nangang → Hsinchu 早晨通勤 |
| `EOB` | `cfg/EOB.md` | End of Business：Hsinchu → Nangang 傍晚通勤 |

讀取的欄位：`-f`（起程站）、`-t`（到達站）、`-T`（時間編號）、`-a`（成人票數）、`-i`（身分證）、`-m`（會員）、`-p`（手機）。

---

## 星期幾時段自動調整（SOB profile）

| 星期 | 時段編號 T | 對應搜尋時間 | 說明 |
|---|---|---|---|
| 週一～週四 | `6` | 07:30 | 搜尋 ~07:25 早鳥班次 |
| 週五 | `3` | 06:00 | 搜尋 ~06:15 早鳥班次 |
| 週六～週日 | 無覆寫（使用設定檔 `-T`） | — | |

> EOB profile 不做星期覆寫，固定使用設定檔的 `-T` 值。

---

## 自動化行為

### 歷史記錄

- 啟動時仍會顯示 TinyDB 歷史紀錄（供日誌確認）
- 自動模式下 **不顯示選擇提示**，直接略過（不套用歷史）
- 所有參數均由 `cfg/{profile}.md` 與 `--date` 提供，無需歷史填補

### 驗證碼（auto_captcha）

- 固定啟用 `auto_captcha=True`
- 使用 ddddocr OCR 辨識結果，**不顯示確認提示**，直接使用
- 辨識失敗（空字串）→ 拋出 `CaptchaError` → 結束，exit code `1`

### 班次選擇（require_discount）

- 預設啟用 `require_discount=True`（使用 `--no-discount` 可關閉）
- 從班次清單中依序找第一個 `discount_str` 包含 `8折` 或 `65折` 的班次並自動選擇
- 找不到符合條件的班次 → 拋出 `NoDiscountError` → 結束，exit code `2`
- 使用 `--no-discount` 時選擇清單第一班（與互動模式預設行為相同）

---

## 結束代碼

| Exit Code | 原因 |
|---|---|
| `0` | 訂票成功 |
| `1` | 驗證碼自動辨識失敗 或 設定檔不存在 或 日期格式錯誤 |
| `2` | 找不到符合 8折／65折 優惠條件的班次 |

---

## 執行日誌範例

```
[auto] profile=SOB  date=2026-04-21 (Tue)  T=6  f=1 → t=5  require_discount=True
請稍等...
驗證碼圖片已儲存：C:\Users\cfkang\Downloads\thsr_captcha.png (及 thsr_captcha_clean.png)
自動辨識驗證碼：AB3K
 1. 0217 07:25~08:21  56分 (8折優惠)
 2. 0219 07:47~08:43  56分
自動選擇優惠班次：217 07:25~08:21 (8折優惠)
...
```

---

## 相關檔案

| 檔案 | 說明 |
|---|---|
| `scripts/book_auto.py` | 本腳本 |
| `cfg/SOB.md` | Start of Business 預設參數 |
| `cfg/EOB.md` | End of Business 預設參數 |
| `thsr_ticket/exceptions.py` | `CaptchaError`、`NoDiscountError` 定義 |
| `thsr_ticket/controller/first_page_flow.py` | `_input_security_code()` auto_captcha 模式 |
| `thsr_ticket/controller/confirm_train_flow.py` | `select_available_trains()` require_discount 模式 |
