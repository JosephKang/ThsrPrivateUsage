import json
from typing import Dict, List, Optional, Tuple

from bs4 import BeautifulSoup
from requests.models import Response
from thsr_ticket.configs.web.param_schema import ConfirmTicketModel

from thsr_ticket.model.db import Record
from thsr_ticket.remote.http_request import HTTPRequest

_MEMBER_RADIO_NAME = (
    'TicketMemberSystemInputPanel:TakerMemberSystemDataView:memberSystemRadioGroup'
)


class ConfirmTicketFlow:
    def __init__(self, client: HTTPRequest, train_resp: Response, record: Record = None, args=None):
        self.client = client
        self.train_resp = train_resp
        self.record = record
        self.args = args

    def run(self) -> Tuple[Response, ConfirmTicketModel]:
        page = BeautifulSoup(self.train_resp.content, features='html.parser')
        personal_id = self.set_personal_id()

        radio_val, membership_extra = _select_member_radio(page, personal_id, self.args)
        ticket_model = ConfirmTicketModel(
            personal_id=personal_id,
            phone_num=self.set_phone_num(),
            member_radio=radio_val,
        )

        dict_params = json.loads(ticket_model.json(by_alias=True))

        if membership_extra:
            dict_params.update(membership_extra)

        early_bird_extra = _process_early_bird(page, personal_id, self.args)
        if early_bird_extra:
            dict_params.update(early_bird_extra)

        resp = self.client.submit_ticket(dict_params)
        return resp, ticket_model

    def set_personal_id(self) -> str:
        if self.record and (personal_id := self.record.personal_id):
            return personal_id
        if self.args and (raw := getattr(self.args, 'id', None)):
            pid = raw.split('|')[0].strip()
            print(f'身分證字號：{pid}')
            return pid
        return input('輸入身分證字號：\n')

    def set_phone_num(self) -> str:
        if self.record and (phone_num := self.record.phone):
            return phone_num
        if self.args and (phone := getattr(self.args, 'phone', None)):
            print(f'手機號碼：{phone}')
            return phone
        if phone_num := input('輸入手機號碼（預設：""）：\n'):
            return phone_num
        return ''


def _select_member_radio(
    page: BeautifulSoup, personal_id: str, args=None
) -> Tuple[str, Optional[Dict[str, str]]]:
    if args and (m := getattr(args, 'membership', None)):
        use_membership = (m == 'y')
        print(f'使用高鐵會員：{"是" if use_membership else "否"}')
    else:
        use_membership = input('使用高鐵會員？(y/n，預設 n)：').strip().lower() == 'y'

    selector_id = 'memberSystemRadio1' if use_membership else 'memberSystemRadio3'
    tag = page.find('input', attrs={'id': selector_id})
    radio_val = tag.attrs['value']

    if use_membership:
        extra = {
            f'{_MEMBER_RADIO_NAME}:memberShipNumber': personal_id,
            f'{_MEMBER_RADIO_NAME}:memberSystemShipCheckBox': 'on',
        }
        return radio_val, extra

    return radio_val, None


def _process_early_bird(
    page: BeautifulSoup, personal_id: str, args=None
) -> Optional[Dict[str, str]]:
    early_bird_elements = page.select('.superEarlyBird')
    if not early_bird_elements:
        return None

    early_type_name = (
        'TicketPassengerInfoInputPanel:passengerDataView:0'
        ':passengerDataView2:passengerDataTypeName'
    )
    early_type_tag = page.find('input', attrs={'name': early_type_name})
    early_type = early_type_tag.attrs['value']

    # Parse ID list from CLI arg (first entry already used as personal_id)
    cli_ids: List[str] = []
    if args and (raw := getattr(args, 'id', None)):
        cli_ids = [s.strip() for s in raw.split('|')]

    def _passenger_fields(i: int, pid: str) -> Dict[str, str]:
        prefix = f'TicketPassengerInfoInputPanel:passengerDataView:{i}:passengerDataView2'
        return {
            f'{prefix}:passengerDataLastName': '',
            f'{prefix}:passengerDataFirstName': '',
            f'{prefix}:passengerDataTypeName': early_type,
            f'{prefix}:passengerDataIdNumber': pid,
            f'{prefix}:passengerDataInputChoice': '0',
        }

    payload: Dict[str, str] = {}

    # Passenger 0: use CLI id[0] (== personal_id) or prompt
    auto = args and getattr(args, 'auto_captcha', False)
    if cli_ids:
        p0_id = cli_ids[0]
        if auto:
            print(f'乘客 1 身份證：{p0_id}')
        else:
            confirm = input(f'乘客 1 身份證（預設：{p0_id}）：').strip()
            p0_id = confirm or p0_id
    else:
        p0_input = input(f'乘客 1 身份證（預設：{personal_id}）：').strip()
        p0_id = p0_input or personal_id
    payload.update(_passenger_fields(0, p0_id))

    # Passengers 1+: use CLI id[i] if available, else prompt
    for i in range(1, len(early_bird_elements)):
        if i < len(cli_ids) and cli_ids[i]:
            pid = cli_ids[i]
            print(f'乘客 {i + 1} 身份證：{pid}')
        else:
            while True:
                pid = input(f'乘客 {i + 1} 身份證（不可空白）：').strip()
                if pid:
                    break
                print('身份證不可空白，請重新輸入。')
        payload.update(_passenger_fields(i, pid))

    return payload
