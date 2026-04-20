import io
import json
import os
import tempfile
import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter
from skimage.morphology import remove_small_objects
from typing import Tuple
from datetime import date, timedelta

from bs4 import BeautifulSoup
from requests.models import Response

from thsr_ticket.exceptions import CaptchaError
from thsr_ticket.model.db import Record
from thsr_ticket.remote.http_request import HTTPRequest
from thsr_ticket.configs.web.param_schema import BookingModel
from thsr_ticket.configs.web.parse_html_element import BOOKING_PAGE
from thsr_ticket.configs.web.enums import StationMapping, TicketType
from thsr_ticket.configs.common import (
    AVAILABLE_TIME_TABLE,
    DAYS_BEFORE_BOOKING_AVAILABLE,
    MAX_TICKET_NUM,
)


class FirstPageFlow:
    def __init__(self, client: HTTPRequest, record: Record = None, args=None) -> None:
        self.client = client
        self.record = record
        self.args = args

    def run(self) -> Tuple[Response, BookingModel]:
        # First page. Booking options
        print('請稍等...')
        book_page = self.client.request_booking_page().content
        img_resp = self.client.request_security_code_img(book_page).content
        page = BeautifulSoup(book_page, features='html.parser')

        book_model = BookingModel(
            start_station=self.select_station('啟程'),
            dest_station=self.select_station('到達', default_value=StationMapping.Zuouing.value),
            outbound_date=self.select_date('出發'),
            outbound_time=self.select_time('啟程'),
            adult_ticket_num=self.select_ticket_num(TicketType.ADULT),
            seat_prefer=_parse_seat_prefer_value(page),
            types_of_trip=_parse_types_of_trip_value(page),
            search_by=_parse_search_by(page),
            security_code=_input_security_code(img_resp, self.args),
        )
        json_params = book_model.json(by_alias=True)
        dict_params = json.loads(json_params)
        resp = self.client.submit_booking_form(dict_params)
        return resp, book_model

    def select_station(self, travel_type: str, default_value: int = StationMapping.Taipei.value) -> int:
        if (
            self.record
            and (
                station := {
                    '啟程': self.record.start_station,
                    '到達': self.record.dest_station,
                }.get(travel_type)
            )
        ):
            return station

        arg_val = {'啟程': getattr(self.args, 'from_station', None),
                   '到達': getattr(self.args, 'to_station', None)}.get(travel_type)
        if arg_val is not None:
            print(f'選擇{travel_type}站：{arg_val}')
            return arg_val

        print(f'選擇{travel_type}站：')
        for station in StationMapping:
            print(f'{station.value}. {station.name}')

        return int(
            input(f'輸入選擇(預設: {default_value})：')
            or default_value
        )

    def select_date(self, date_type: str) -> str:
        today = date.today()
        last_avail_date = today + timedelta(days=DAYS_BEFORE_BOOKING_AVAILABLE)

        arg_val = getattr(self.args, 'date', None)
        if arg_val is not None:
            print(f'選擇{date_type}日期：{arg_val}')
            return arg_val

        print(f'選擇{date_type}日期（{today}~{last_avail_date}）（預設為今日）：')
        return input() or str(today)

    def select_time(self, time_type: str, default_value: int = 10) -> str:
        if self.record and (
            time_str := {
                '啟程': self.record.outbound_time,
                '回程': None,
            }.get(time_type)
        ):
            return time_str

        arg_val = getattr(self.args, 'time', None)
        if arg_val is not None:
            selected = AVAILABLE_TIME_TABLE[arg_val - 1]
            print(f'選擇出發時間：{arg_val} ({selected})')
            return selected

        print('選擇出發時間：')
        for idx, t_str in enumerate(AVAILABLE_TIME_TABLE):
            t_int = int(t_str[:-1])
            if t_str[-1] == "A" and (t_int // 100) == 12:
                t_int = "{:04d}".format(t_int % 1200)  # type: ignore
            elif t_int != 1230 and t_str[-1] == "P":
                t_int += 1200
            t_str = str(t_int)
            print(f'{idx+1}. {t_str[:-2]}:{t_str[-2:]}')

        selected_opt = int(input(f'輸入選擇（預設：{default_value}）：') or default_value)
        return AVAILABLE_TIME_TABLE[selected_opt-1]

    def select_ticket_num(self, ticket_type: TicketType, default_ticket_num: int = 1) -> str:
        if self.record and (
            ticket_num_str := {
                TicketType.ADULT: self.record.adult_num,
                TicketType.CHILD: None,
                TicketType.DISABLED: None,
                TicketType.ELDER: None,
                TicketType.COLLEGE: None,
            }.get(ticket_type)
        ):
            return ticket_num_str

        # Priority: --adult > len(--id) > interactive
        arg_val = getattr(self.args, 'adult', None)
        if arg_val is None and ticket_type == TicketType.ADULT:
            if raw_id := getattr(self.args, 'id', None):
                arg_val = len(raw_id.split('|'))
        if arg_val is not None:
            ticket_type_name = {
                TicketType.ADULT: '成人',
            }.get(ticket_type, str(ticket_type))
            print(f'選擇{ticket_type_name}票數：{arg_val}')
            return f'{arg_val}{ticket_type.value}'

        ticket_type_name = {
            TicketType.ADULT: '成人',
            TicketType.CHILD: '孩童',
            TicketType.DISABLED: '愛心',
            TicketType.ELDER: '敬老',
            TicketType.COLLEGE: '大學生',
        }.get(ticket_type)

        print(f'選擇{ticket_type_name}票數（0~{MAX_TICKET_NUM}）（預設：{default_ticket_num}）')
        ticket_num = int(input() or default_ticket_num)
        return f'{ticket_num}{ticket_type.value}'


def _parse_seat_prefer_value(page: BeautifulSoup) -> str:
    options = page.find(**BOOKING_PAGE["seat_prefer_radio"])
    preferred_seat = options.find_next(selected='selected')
    return preferred_seat.attrs['value']


def _parse_types_of_trip_value(page: BeautifulSoup) -> int:
    options = page.find(**BOOKING_PAGE["types_of_trip"])
    tag = options.find_next(selected='selected')
    return int(tag.attrs['value'])


def _parse_search_by(page: BeautifulSoup) -> str:
    candidates = page.find_all('input', {'name': 'bookingMethod'})
    tag = next((cand for cand in candidates if 'checked' in cand.attrs))
    return tag.attrs['value']


def _input_security_code(img_resp: bytes, args=None) -> str:
    image = Image.open(io.BytesIO(img_resp))
    cleaned = _preprocess_captcha(image)
    _save_captcha_for_windows(image, cleaned)

    predicted = _ddddocr_recognize(img_resp, cleaned)

    if getattr(args, 'auto_captcha', False):
        if not predicted:
            raise CaptchaError('驗證碼自動辨識失敗')
        print(f'自動辨識驗證碼：{predicted}')
        return predicted

    if predicted:
        print(f'自動辨識驗證碼：{predicted}')
        confirm = input('按 Enter 確認，或輸入修正值：').strip()
        return confirm if confirm else predicted

    print('自動辨識失敗，請手動輸入驗證碼：')
    _print_image_ascii_2(cleaned, cols=80)
    return input()


def _save_captcha_for_windows(image: Image.Image, cleaned: Image.Image) -> None:
    win_users = '/mnt/c/Users'
    save_dir = None
    if os.path.isdir(win_users):
        for entry in os.listdir(win_users):
            candidate = os.path.join(win_users, entry, 'Downloads')
            if os.path.isdir(candidate):
                save_dir = candidate
                break
    if save_dir is None:
        save_dir = tempfile.gettempdir()

    scale = 4
    for suffix, img in [('', image), ('_clean', cleaned)]:
        path = os.path.join(save_dir, f'thsr_captcha{suffix}.png')
        enlarged = img.resize((img.width * scale, img.height * scale), Image.NEAREST)
        enlarged.save(path)

    path = os.path.join(save_dir, 'thsr_captcha.png')
    if path.startswith('/mnt/c/'):
        win_path = 'C:\\' + path[len('/mnt/c/'):].replace('/', '\\')
        print(f'驗證碼圖片已儲存：{win_path} (及 thsr_captcha_clean.png)')
    else:
        print(f'驗證碼圖片已儲存：{path}')


def _ddddocr_recognize(raw_bytes: bytes, cleaned: Image.Image) -> str:
    try:
        import ddddocr
        ocr = ddddocr.DdddOcr(show_ad=False)
        buf = io.BytesIO()
        cleaned.save(buf, format='PNG')
        result = ocr.classification(buf.getvalue()).upper().strip()
        return result if len(result) == 4 else ''
    except Exception:
        return ''


def _preprocess_captcha(image: Image.Image) -> Image.Image:
    arr = np.array(image.convert('L'))

    # Step 2: median blur — removes salt-and-pepper noise
    arr = cv2.medianBlur(arr, 3)

    # Step 3: Otsu binarization — auto threshold, text=black bg=white
    _, arr = cv2.threshold(arr, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # Step 4: morphological opening — remove residual small noise dots
    kernel = np.ones((2, 2), np.uint8)
    arr = cv2.morphologyEx(arr, cv2.MORPH_OPEN, kernel)

    # Step 5: remove small objects — area-based noise removal
    # skimage expects bool array with True = foreground (text = dark = 0)
    text_mask = arr == 0
    cleaned_mask = remove_small_objects(text_mask, max_size=50)
    arr = np.where(cleaned_mask, 0, 255).astype(np.uint8)

    return Image.fromarray(arr)


def _print_image_ascii(image: Image.Image, cols: int = 80) -> None:
    image = image.convert('L')
    rows = int(cols * image.height / image.width)
    if rows % 2:
        rows += 1
    image = image.resize((cols, rows))

    threshold = 128
    for y in range(0, rows, 2):
        row = ''
        for x in range(cols):
            top = image.getpixel((x, y)) < threshold
            bot = image.getpixel((x, y + 1)) < threshold
            #if top and bot:
            #    row += ' '
            #elif top:
            #    row += '▄'
            #elif bot:
            #    row += '▀'
            #else:
            #    row += '█'
            if top and bot:
                row += '█'
            elif top:
                row += '▀'
            elif bot:
                row += '▄'
            else:
                row += ' '
        print(row)


def _print_image_ascii_1(image: Image.Image, cols: int = 80) -> None:
    """Option 1: ANSI color background, fixed threshold."""
    image = image.convert('L')
    rows = int(cols * image.height / image.width)
    image = image.resize((cols, rows))

    threshold = 128
    RESET = '\033[0m'
    WHITE_BG = '\033[47m'
    BLACK_BG = '\033[40m'
    for y in range(rows):
        row = ''
        for x in range(cols):
            dark = image.getpixel((x, y)) < threshold
            row += (WHITE_BG if dark else BLACK_BG) + ' '
        print(row + RESET)


def _print_image_ascii_2(image: Image.Image, cols: int = 80) -> None:
    """Option 2: Braille unicode (2x4 pixels per char)."""
    image = image.convert('L')
    px_cols = cols * 2
    px_rows = int(px_cols * image.height / image.width)
    if px_rows % 4:
        px_rows += 4 - (px_rows % 4)
    image = image.resize((px_cols, px_rows))

    threshold = 128
    # Braille dot-to-bit mapping for a 2-wide x 4-tall cell
    dot_map = [
        (0, 0, 0x01), (0, 1, 0x02), (0, 2, 0x04), (0, 3, 0x40),
        (1, 0, 0x08), (1, 1, 0x10), (1, 2, 0x20), (1, 3, 0x80),
    ]
    for cy in range(px_rows // 4):
        row = ''
        for cx in range(cols):
            bits = 0
            for dc, dr, bit in dot_map:
                if image.getpixel((cx * 2 + dc, cy * 4 + dr)) < threshold:
                    bits |= bit
            row += chr(0x2800 + bits)
        print(row)


def _otsu_threshold(image: Image.Image) -> int:
    histogram = image.histogram()
    total = image.width * image.height
    sum_total = sum(i * histogram[i] for i in range(256))
    sum_bg, weight_bg, threshold = 0.0, 0, 0
    max_variance = 0.0
    for i in range(256):
        weight_bg += histogram[i]
        if weight_bg == 0:
            continue
        weight_fg = total - weight_bg
        if weight_fg == 0:
            break
        sum_bg += i * histogram[i]
        mean_bg = sum_bg / weight_bg
        mean_fg = (sum_total - sum_bg) / weight_fg
        variance = weight_bg * weight_fg * (mean_bg - mean_fg) ** 2
        if variance > max_variance:
            max_variance = variance
            threshold = i
    return threshold


def _print_image_ascii_1_3(image: Image.Image, cols: int = 80) -> None:
    """Option 1 + 3: ANSI color background with Otsu adaptive threshold."""
    image = image.convert('L')
    rows = int(cols * image.height / image.width)
    image = image.resize((cols, rows))

    threshold = _otsu_threshold(image)
    RESET = '\033[0m'
    WHITE_BG = '\033[47m'
    BLACK_BG = '\033[40m'
    for y in range(rows):
        row = ''
        for x in range(cols):
            dark = image.getpixel((x, y)) < threshold
            row += (WHITE_BG if dark else BLACK_BG) + ' '
        print(row + RESET)


def _print_image_ascii_1_4(image: Image.Image, cols: int = 80) -> None:
    """Option 1 + 4: ANSI color background with contrast/sharpen preprocessing."""
    image = image.convert('L')
    image = ImageEnhance.Contrast(image).enhance(2.0)
    image = image.filter(ImageFilter.SHARPEN)
    rows = int(cols * image.height / image.width)
    image = image.resize((cols, rows))

    threshold = 128
    RESET = '\033[0m'
    WHITE_BG = '\033[47m'
    BLACK_BG = '\033[40m'
    for y in range(rows):
        row = ''
        for x in range(cols):
            dark = image.getpixel((x, y)) < threshold
            row += (WHITE_BG if dark else BLACK_BG) + ' '
        print(row + RESET)
