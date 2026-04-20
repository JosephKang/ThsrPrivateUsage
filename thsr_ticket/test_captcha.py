import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

import ddddocr
from PIL import Image

from thsr_ticket.controller.first_page_flow import _preprocess_captcha, _print_image_ascii_2

TEST_DIR = "/mnt/c/Users/Chia-Feng Kang/Downloads/20260404"
GROUND_TRUTH = {
    "thsr_captcha_0.png": "D7K9",
    "thsr_captcha_1.png": "243M",
    "thsr_captcha_2.png": "ZGW4",
    "thsr_captcha_3.png": "T4K5",
    "thsr_captcha_4.png": "GR23",
    "thsr_captcha_5.png": "DMMT",
    "thsr_captcha_6.png": "75RK",
    "thsr_captcha_7.png": "DRHW",
    "thsr_captcha_8.png": "WWPK",
    "thsr_captcha_9.png": "WDVF",
}

ocr = ddddocr.DdddOcr(show_ad=False)

char_correct = 0
char_total = 0
img_correct = 0

print("=" * 60)
for filename, expected in GROUND_TRUTH.items():
    path = os.path.join(TEST_DIR, filename)
    image = Image.open(path)
    cleaned = _preprocess_captcha(image)

    with open(path, 'rb') as f:
        raw_bytes = f.read()

    import io
    buf = io.BytesIO()
    cleaned.save(buf, format='PNG')
    cleaned_bytes = buf.getvalue()

    predicted_raw = ocr.classification(raw_bytes).upper().strip()
    predicted_clean = ocr.classification(cleaned_bytes).upper().strip()

    img_match = predicted_clean == expected
    if img_match:
        img_correct += 1

    chars_match = sum(a == b for a, b in zip(predicted_clean.ljust(len(expected)), expected))
    char_correct += chars_match
    char_total += len(expected)

    status = "✓" if img_match else "✗"
    print(f"{status} {filename}  expected={expected}  raw={predicted_raw}  clean={predicted_clean}")
    if not img_match:
        print(f"  --- original ---")
        _print_image_ascii_2(image, cols=40)
        print(f"  --- preprocessed ---")
        _print_image_ascii_2(cleaned, cols=40)

print("=" * 60)
print(f"Image accuracy : {img_correct}/{len(GROUND_TRUTH)} ({img_correct/len(GROUND_TRUTH)*100:.0f}%)")
print(f"Char  accuracy : {char_correct}/{char_total} ({char_correct/char_total*100:.0f}%)")
