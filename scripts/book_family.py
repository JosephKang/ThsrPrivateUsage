#!/usr/bin/env python3
"""Family booking script for THSR.

Hardcoded route: 台南 (11) → 南港 (1), date defaults to 2026-05-03.
Accepts --time as HH:MM (e.g. 14:00), auto-selects first returned train.

Exit codes:
  0  Success
  1  CAPTCHA recognition failed
"""

import argparse
import sys
import os
from argparse import Namespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from thsr_ticket.controller.booking_flow import BookingFlow
from thsr_ticket.exceptions import CaptchaError

FROM_STATION  = 11            # 台南 Tainan
TO_STATION    = 1             # 南港 Nangang
DEFAULT_DATE  = '2026-05-03'
DEFAULT_PHONE = '0953747258'

# Time string → 1-based slot index (matches cfg/time_table.md)
_TIME_TO_SLOT: dict[str, int] = {'00:01': 1, '00:30': 2}
_TIME_TO_SLOT.update({
    f'{h:02d}:{m:02d}': idx
    for idx, (h, m) in enumerate(
        ((h, m) for h in range(6, 24) for m in (0, 30)),
        start=3,
    )
})


def _parse_time(time_str: str) -> int:
    slot = _TIME_TO_SLOT.get(time_str)
    if slot is None:
        raise argparse.ArgumentTypeError(
            f'無效時間 "{time_str}"，請使用 HH:MM 格式（如 14:00）'
        )
    return slot


def main() -> int:
    parser = argparse.ArgumentParser(description='THSR family booking: 台南→南港')
    parser.add_argument('--date', '-d', default=DEFAULT_DATE,
                        help=f'出發日期 YYYY-MM-DD（預設 {DEFAULT_DATE}）')
    parser.add_argument('--time', '-T', required=True, type=_parse_time,
                        metavar='HH:MM',
                        help='出發時間，如 14:00')
    parser.add_argument('--adult', '-a', type=int, required=True,
                        help='成人票數（1–10）')
    parser.add_argument('--id', '-i', required=True,
                        help='身分證字號，多人用 | 分隔（第一筆為訂票人/會員）')
    parser.add_argument('--membership', '-m', choices=['y', 'n'], default='y',
                        help='使用高鐵會員（預設 y）')
    parser.add_argument('--phone', '-p', default=DEFAULT_PHONE,
                        help=f'手機號碼（預設 {DEFAULT_PHONE}）')
    cli = parser.parse_args()

    date_str = cli.date.replace('/', '-')

    ns = Namespace(
        from_station=FROM_STATION,
        to_station=TO_STATION,
        date=date_str,
        time=cli.time,
        adult=cli.adult,
        id=cli.id,
        membership=cli.membership,
        phone=cli.phone,
        auto_captcha=True,
        require_discount=False,
        auto_train=True,
        min_depart=None,
        max_depart=None,
    )

    print(f'[family] date={date_str}  T={cli.time}  '
          f'f={FROM_STATION}(台南) → t={TO_STATION}(南港)  '
          f'adult={cli.adult}  membership={cli.membership}')

    try:
        BookingFlow(args=ns).run()
    except CaptchaError as e:
        print(f'[family] 驗證碼失敗：{e}', file=sys.stderr)
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
