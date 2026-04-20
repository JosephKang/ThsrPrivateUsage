#!/usr/bin/env python3
"""Auto-booking script for THSR.

Reads default parameters from cfg/SOB.md or cfg/EOB.md, accepts a --date
argument, adjusts the departure time slot based on the day of the week,
and runs a fully automated booking (no interactive prompts).

Exit codes:
  0  Success
  1  CAPTCHA recognition failed
  2  No qualifying discount train found (8折 / 65折)
"""

import argparse
import re
import sys
import os
from argparse import Namespace
from datetime import datetime

# Allow running as `python scripts/book_auto.py` from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from thsr_ticket.controller.booking_flow import BookingFlow
from thsr_ticket.exceptions import CaptchaError, NoDiscountError

# Weekday overrides for SOB profile (Mon=0 … Sun=6)
# Tuple: (T, min_depart, max_depart)
# Weekdays absent from the table → booking is refused (exit 2)
_SOB_TIME_OVERRIDE = {
    0: (6, '07:25', '07:50'),   # Mon
    1: (6, '07:25', '07:50'),   # Tue
    2: (6, '07:25', '07:50'),   # Wed
    3: (6, '07:25', '07:50'),   # Thu
    4: (3, '06:15', '07:10'),   # Fri
}

# Weekday overrides for EOB profile (Mon=0 … Sun=6)
# Tuple: (T, min_depart, max_depart)
# Weekdays absent from the table → booking is refused (exit 2)
_EOB_TIME_OVERRIDE = {
    0: (25, '17:39', '18:00'),   # Mon
    1: (25, '17:39', '18:00'),   # Tue
    2: (25, '17:39', '18:00'),   # Wed
    3: (25, '17:39', '18:00'),   # Thu
    4: (24, '16:39', '17:10'),   # Fri
}


def _parse_md_defaults(md_path: str) -> dict:
    """Extract CLI flag → value from a markdown table like cfg/SOB.md."""
    params = {}
    with open(md_path, encoding='utf-8') as f:
        for line in f:
            # Match lines like: | 起程站 | `-f` | `1` (Nangang 南港) |
            m = re.match(r'\|\s*[^|]+\|\s*`(-\w+)`\s*\|\s*`([^`\s]+)', line)
            if m:
                params[m.group(1)] = m.group(2)
    return params


def _build_namespace(
    params: dict, date: str,
    time_override: int | None,
    min_depart: str | None = None,
    max_depart: str | None = None,
) -> Namespace:
    """Convert parsed flag-value dict + date into an argparse Namespace."""
    def _int(key: str, default=None):
        v = params.get(key)
        return int(v) if v is not None else default

    T = time_override if time_override is not None else _int('-T')

    return Namespace(
        from_station=_int('-f'),
        to_station=_int('-t'),
        date=date,
        time=T,
        adult=_int('-a'),
        id=params.get('-i'),
        membership=params.get('-m'),
        phone=params.get('-p', ''),
        auto_captcha=True,
        require_discount=True,
        min_depart=min_depart,
        max_depart=max_depart,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description='THSR auto-booking script')
    parser.add_argument(
        '--date', '-d', required=True,
        help='Departure date (YYYY-MM-DD or YYYY/MM/DD)',
    )
    parser.add_argument(
        '--profile', choices=['SOB', 'EOB'], default='SOB',
        help='Booking profile (default: SOB)',
    )
    parser.add_argument(
        '--no-discount', action='store_true',
        help='Skip discount requirement — accept any train',
    )
    cli = parser.parse_args()

    # Resolve profile config file relative to project root
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    cfg_path = os.path.join(project_root, 'cfg', f'{cli.profile}.md')

    if not os.path.exists(cfg_path):
        print(f'錯誤：找不到設定檔 {cfg_path}', file=sys.stderr)
        return 1

    params = _parse_md_defaults(cfg_path)

    # Normalise date and compute weekday override for SOB
    date_str = cli.date.replace('/', '-')
    try:
        departure_date = datetime.strptime(date_str, '%Y-%m-%d')
    except ValueError:
        print(f'錯誤：日期格式不正確：{cli.date}（請使用 YYYY-MM-DD）', file=sys.stderr)
        return 1

    override_map = {'SOB': _SOB_TIME_OVERRIDE, 'EOB': _EOB_TIME_OVERRIDE}
    weekday_name = departure_date.strftime('%a')
    entry = override_map.get(cli.profile, {}).get(departure_date.weekday())
    if entry is None:
        print(f'[auto] 拒絕訂票：{date_str} ({weekday_name}) 不在 {cli.profile} 的訂票時段內', file=sys.stderr)
        return 2

    time_override, min_depart, max_depart = entry
    ns = _build_namespace(params, date_str, time_override, min_depart, max_depart)
    if cli.no_discount:
        ns.require_discount = False

    print(f'[auto] profile={cli.profile}  date={date_str} ({weekday_name})  T={ns.time}  '
          f'f={ns.from_station} → t={ns.to_station}  require_discount={ns.require_discount}  '
          f'depart={ns.min_depart}~{ns.max_depart}')

    try:
        BookingFlow(args=ns).run()
    except CaptchaError as e:
        print(f'[auto] 驗證碼失敗：{e}', file=sys.stderr)
        return 1
    except NoDiscountError as e:
        print(f'[auto] 無優惠班次：{e}', file=sys.stderr)
        return 2

    return 0


if __name__ == '__main__':
    sys.exit(main())
