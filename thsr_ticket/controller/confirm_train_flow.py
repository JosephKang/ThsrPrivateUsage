import json
from typing import List, Tuple

from requests.models import Response

from thsr_ticket.exceptions import NoAvailableTrainsError, NoDiscountError
from thsr_ticket.remote.http_request import HTTPRequest
from thsr_ticket.view_model.avail_trains import AvailTrains
from thsr_ticket.configs.web.param_schema import Train, ConfirmTrainModel


_DISCOUNT_KEYWORDS = ['8折', '65折']


class ConfirmTrainFlow:
    def __init__(self, client: HTTPRequest, book_resp: Response, args=None):
        self.client = client
        self.book_resp = book_resp
        self.args = args

    def run(self) -> Tuple[Response, ConfirmTrainModel]:
        trains = AvailTrains().parse(self.book_resp.content)
        if not trains:
            raise NoAvailableTrainsError('No available trains!')

        confirm_model = ConfirmTrainModel(
            selected_train=self.select_available_trains(trains),
        )
        json_params = confirm_model.json(by_alias=True)
        dict_params = json.loads(json_params)
        resp = self.client.submit_train(dict_params)
        return resp, confirm_model

    def select_available_trains(self, trains: List[Train], default_value: int = 1) -> Train:
        for idx, train in enumerate(trains, 1):
            print(
                f'{idx}. {train.id:>4} {train.depart:>3}~{train.arrive} {train.travel_time:>3} '
                f'{train.discount_str}'
            )

        if getattr(self.args, 'require_discount', False):
            min_depart = getattr(self.args, 'min_depart', None)
            max_depart = getattr(self.args, 'max_depart', None)
            for train in trains:
                if min_depart and train.depart < min_depart:
                    continue
                if max_depart and train.depart > max_depart:
                    continue
                if any(kw in train.discount_str for kw in _DISCOUNT_KEYWORDS):
                    print(f'自動選擇優惠班次：{train.id} {train.depart}~{train.arrive} {train.discount_str}')
                    return train.form_value
            window = f'{min_depart}~{max_depart}' if min_depart else ''
            raise NoDiscountError(f'無符合條件的優惠班次（8折／65折）{f"（{window}）" if window else ""}')

        selection = int(input(f'輸入選擇（預設：{default_value}）：') or default_value)
        return trains[selection-1].form_value
