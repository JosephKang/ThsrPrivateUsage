import sys
import argparse
sys.path.append("./")

from thsr_ticket.controller.booking_flow import BookingFlow


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='台灣高鐵自動訂票工具',
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument('-f', '--from-station', type=int, metavar='STATION_ID',
                        help='起程站編號 (1=南港 … 12=左營)')
    parser.add_argument('-t', '--to-station', type=int, metavar='STATION_ID',
                        help='到達站編號 (1=南港 … 12=左營)')
    parser.add_argument('-d', '--date', type=str, metavar='DATE',
                        help='出發日期，格式：YYYY-MM-DD 或 YYYY/MM/DD')
    parser.add_argument('-T', '--time', type=int, metavar='TIME_ID',
                        help='出發時間編號（1-based，執行 --list-time-table 查看）')
    parser.add_argument('-a', '--adult', type=int, metavar='N',
                        help='成人票數（0~10，預設 1）')
    parser.add_argument('-i', '--id', type=str, metavar='ID[|ID2|...]',
                        help='身分證字號，多筆以 | 分隔\n'
                             '  第一筆：訂票人 / 早鳥乘客 1\n'
                             '  第二筆起：早鳥乘客 2, 3, …')
    parser.add_argument('-m', '--membership', type=str, choices=['y', 'n'],
                        metavar='y/n',
                        help='使用高鐵會員 (y=使用, n=不使用)，不提供則互動詢問')
    parser.add_argument('-p', '--phone', type=str, metavar='PHONE',
                        help='手機號碼（選填，格式：09XXXXXXXX）')
    parser.add_argument('--list-station', action='store_true',
                        help='列出所有車站編號後離開')
    parser.add_argument('--list-time-table', action='store_true',
                        help='列出所有時間編號後離開')
    return parser


def _list_stations() -> None:
    from thsr_ticket.configs.web.enums import StationMapping
    for s in StationMapping:
        print(f'{s.value:>2}. {s.name}')


def _list_time_table() -> None:
    from thsr_ticket.configs.common import AVAILABLE_TIME_TABLE
    for idx, t_str in enumerate(AVAILABLE_TIME_TABLE, 1):
        t_int = int(t_str[:-1])
        if t_str[-1] == 'A' and (t_int // 100) == 12:
            t_int = t_int % 1200
        elif t_int != 1230 and t_str[-1] == 'P':
            t_int += 1200
        t_fmt = f'{t_int:04d}'
        print(f'{idx:>2}. {t_fmt[:-2]}:{t_fmt[-2:]}')


def main(args=None) -> None:
    parser = _build_parser()
    ns = parser.parse_args(args)

    if ns.list_station:
        _list_stations()
        return

    if ns.list_time_table:
        _list_time_table()
        return

    flow = BookingFlow(args=ns)
    flow.run()


if __name__ == '__main__':
    main()
