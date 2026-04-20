# CAPTCHA 自動辨識功能規格文件

## 概述

本文件描述在 WSL（Windows Subsystem for Linux）環境下，針對台灣高鐵（THSR）訂票系統驗證碼所開發的自動辨識流程，包含影像預處理、終端顯示、OCR 辨識與備援機制。

---

## 環境背景

- **執行環境**：WSL2（Linux on Windows）
- **問題**：WSL 無法直接彈出視窗（`Image.show()` 失效、`explorer.exe` 無法執行）
- **解法**：多層備援機制（自動 OCR → 終端顯示 → 手動輸入）

---

## CAPTCHA 特徵

| 項目 | 說明 |
|---|---|
| 字元數 | 固定 4 碼 |
| 字元集 | 英文大寫字母 + 數字（0-9, A-Z） |
| 圖片尺寸 | 約 130×45 px |
| 背景 | 淺灰色混雜大量椒鹽雜訊（隨機黑白點） |
| 字體 | 粗體黑色，無干擾線，字元佔圖片大部分高度 |

---

## 整體流程

```
取得驗證碼圖片（bytes）
        │
        ▼
_preprocess_captcha()    ← 影像預處理
        │
        ├──► _save_captcha_for_windows()   ← 儲存原圖 + 清理後圖至 Windows Downloads
        │
        ▼
_ddddocr_recognize()     ← 自動 OCR 辨識
        │
        ├── 成功（4碼結果）
        │       │
        │       ▼
        │   顯示預測值，等待使用者確認或修正
        │
        └── 失敗（非 4 碼 / 例外）
                │
                ▼
            _print_image_ascii_2()   ← 點字終端顯示
                │
                ▼
            等待使用者手動輸入
```

---

## 模組說明

### `_preprocess_captcha(image: Image) -> Image`

**位置**：`thsr_ticket/controller/first_page_flow.py`

影像預處理流水線，接收原始 PIL Image，輸出二值化清理後的 PIL Image。

| 步驟 | 方法 | 目的 |
|---|---|---|
| 1 | `image.convert('L')` + `np.array()` | 轉灰階、轉 NumPy 陣列 |
| 2 | `cv2.medianBlur(arr, 3)` | 中值濾波，消除椒鹽雜訊，保留字元邊緣 |
| 3 | `cv2.threshold(..., THRESH_BINARY + THRESH_OTSU)` | Otsu 自動二值化，背景轉純白、字元轉純黑 |
| 4 | `cv2.morphologyEx(MORPH_OPEN, kernel=2×2)` | 形態學開運算，移除殘留細小雜訊點 |
| 5 | `remove_small_objects(max_size=50)` | 依面積門檻清除殘留雜訊區塊 |

**依賴**：`opencv-python`、`scikit-image`、`numpy`

---

### `_ddddocr_recognize(raw_bytes: bytes, cleaned: Image) -> str`

**位置**：`thsr_ticket/controller/first_page_flow.py`

使用 `ddddocr` 對預處理後圖片進行 OCR 辨識。

- 輸入：原始圖片 bytes（備用）、預處理後 PIL Image
- 輸出：4 碼大寫字串，或空字串（辨識失敗）
- 驗證：結果長度必須為 4，否則視為失敗觸發備援
- 例外處理：任何例外均 catch，返回空字串

**依賴**：`ddddocr`（底層為 `onnxruntime` + 預訓練 ONNX 模型）

---

### `_save_captcha_for_windows(image: Image, cleaned: Image) -> None`

**位置**：`thsr_ticket/controller/first_page_flow.py`

將原始圖與清理後圖儲存至 Windows 使用者的 Downloads 資料夾，供人工比對。

- 自動掃描 `/mnt/c/Users/*/Downloads/` 找到第一個有效路徑
- 儲存 `thsr_captcha.png`（原始，4× 放大）
- 儲存 `thsr_captcha_clean.png`（清理後，4× 放大）
- 放大使用 `Image.NEAREST`（最近鄰插值），保持像素銳利
- 若非 WSL 環境則儲存至系統暫存目錄（`tempfile.gettempdir()`）

---

### `_print_image_ascii_2(image: Image, cols: int = 80) -> None`

**位置**：`thsr_ticket/controller/first_page_flow.py`

以 Unicode 點字字元在終端渲染驗證碼圖片，作為 OCR 失敗時的備援顯示。

| 項目 | 說明 |
|---|---|
| 字元集 | Unicode Braille（U+2800–U+28FF） |
| 解析度 | 每個字元編碼 2×4 像素，等效解析度為 `cols×2` × `rows×4` |
| 門檻值 | 固定 128（二值化後圖片為純黑白，門檻值影響不大） |
| 對應邏輯 | 暗像素（< 128）→ 點，亮像素 → 空白 |
| 預設寬度 | 80 字元（可透過 `cols` 參數調整） |

其他保留的顯示函式（目前未在主流程啟用）：

| 函式 | 方法 |
|---|---|
| `_print_image_ascii` | Unicode 半塊字元（▀▄█），2× 垂直解析度 |
| `_print_image_ascii_1` | ANSI 色彩背景，固定門檻 128 |
| `_print_image_ascii_1_3` | ANSI 色彩背景 + Otsu 自適應門檻 |
| `_print_image_ascii_1_4` | ANSI 色彩背景 + 對比增強 + 銳化前處理 |

---

### `_input_security_code(img_resp: bytes) -> str`

**位置**：`thsr_ticket/controller/first_page_flow.py`

驗證碼輸入的主控函式，整合所有子功能。

```
使用者互動流程：

[自動辨識成功]
  自動辨識驗證碼：D7K9
  按 Enter 確認，或輸入修正值：▌
      → Enter          使用預測值 D7K9
      → 輸入 D7K8      使用修正值 D7K8

[自動辨識失敗]
  自動辨識失敗，請手動輸入驗證碼：
  ⠀⠀⢀⣀⣀⠀⠀⠀⣀⣀⣀⠀...（點字顯示）
  ▌
```

---

## 新增依賴

| 套件 | 版本 | 用途 |
|---|---|---|
| `opencv-python` | 4.13+ | 中值濾波、Otsu 二值化、形態學操作 |
| `scikit-image` | 0.26+ | `remove_small_objects` 雜訊區塊移除 |
| `ddddocr` | 1.6+ | 驗證碼 OCR（底層：onnxruntime + ONNX 模型） |
| `numpy` | 2.4+ | 影像陣列操作（opencv/scikit-image 共同依賴） |

---

## 測試

### 測試腳本

**位置**：`thsr_ticket/test_captcha.py`

**執行方式**：
```bash
.venv/bin/python3 thsr_ticket/test_captcha.py
```

**功能**：
- 讀取 10 張 THSR 真實驗證碼圖片
- 對每張圖分別測試原始圖與預處理後圖的 OCR 結果
- 比對答案，輸出逐圖報告
- 計算圖片級與字元級準確率
- 失敗圖片額外輸出點字顯示供人工比對

### 測試資料集

| 檔名 | 正確答案 |
|---|---|
| thsr_captcha_0.png | D7K9 |
| thsr_captcha_1.png | 243M |
| thsr_captcha_2.png | ZGW4 |
| thsr_captcha_3.png | T4K5 |
| thsr_captcha_4.png | GR23 |
| thsr_captcha_5.png | DMMT |
| thsr_captcha_6.png | 75RK |
| thsr_captcha_7.png | DRHW |
| thsr_captcha_8.png | WWPK |
| thsr_captcha_9.png | WDVF |

### 測試結果（2026-04-04）

| 指標 | 數值 |
|---|---|
| 圖片準確率 | **9/10（90%）** |
| 字元準確率 | **39/40（98%）** |
| 失敗案例 | `thsr_captcha_1.png`：`2` 被誤判為 `Z` |
| 失敗原因 | ddddocr 模型限制，與預處理無關（原始圖亦誤判） |

### 預處理效果

| 圖片 | 原始 OCR | 預處理後 OCR | 正確答案 |
|---|---|---|---|
| thsr_captcha_0.png | U7K9 ✗ | **D7K9 ✓** | D7K9 |
| thsr_captcha_6.png | 7T5RK ✗ | **75RK ✓** | 75RK |

預處理對這兩張圖有明確改善效果。

---

## 已知限制

1. **`2` vs `Z` 混淆**：ddddocr 模型對特定字型的 `2` 辨識為 `Z`，屬模型限制，使用者可在確認提示時修正。
2. **WSL Interop 停用環境**：若 WSL 無法執行任何 Windows 執行檔，自動開啟圖片的功能不可用，已改為儲存至 Downloads 並顯示路徑。
3. **樣本數有限**：目前測試集僅 10 張，準確率為初步估計值。
