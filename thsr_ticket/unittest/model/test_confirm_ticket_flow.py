"""
Tests for ConfirmTicketFlow.run(), _select_member_radio(), and _process_early_bird().

HTML fixtures are minimal inline strings covering only the selectors each function needs.
"""
import json
from unittest.mock import MagicMock, patch

import pytest
from bs4 import BeautifulSoup

from thsr_ticket.controller.confirm_ticket_flow import (
    ConfirmTicketFlow,
    _process_early_bird,
    _select_member_radio,
)

# ---------------------------------------------------------------------------
# HTML fixtures
# ---------------------------------------------------------------------------

_MEMBER_RADIO_HTML = """
<html><body>
  <input type="radio" id="memberSystemRadio1"
    name="TicketMemberSystemInputPanel:TakerMemberSystemDataView:memberSystemRadioGroup"
    value="MEMBER" />
  <input type="radio" id="memberSystemRadio3"
    name="TicketMemberSystemInputPanel:TakerMemberSystemDataView:memberSystemRadioGroup"
    value="NON_MEMBER" checked />
</body></html>
"""

_EARLY_BIRD_1P_HTML = """
<html><body>
  <p class="superEarlyBird"><span>早鳥優惠</span></p>
  <input type="hidden"
    name="TicketPassengerInfoInputPanel:passengerDataView:0:passengerDataView2:passengerDataTypeName"
    value="EARLY_TYPE_A" />
</body></html>
"""

_EARLY_BIRD_2P_HTML = """
<html><body>
  <p class="superEarlyBird"><span>早鳥優惠</span></p>
  <p class="superEarlyBird"><span>早鳥優惠</span></p>
  <input type="hidden"
    name="TicketPassengerInfoInputPanel:passengerDataView:0:passengerDataView2:passengerDataTypeName"
    value="EARLY_TYPE_A" />
</body></html>
"""

_NO_EARLY_BIRD_HTML = """
<html><body>
  <p class="other">無優惠</p>
</body></html>
"""

_FULL_PAGE_HTML = _MEMBER_RADIO_HTML  # reuse — has member radios, no early bird


def _parse(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, features='html.parser')


# ---------------------------------------------------------------------------
# _select_member_radio
# ---------------------------------------------------------------------------

class TestSelectMemberRadio:
    def test_no_member_returns_non_member_value_and_no_extra(self):
        page = _parse(_MEMBER_RADIO_HTML)
        with patch('builtins.input', return_value='n'):
            radio_val, extra = _select_member_radio(page, 'A123456789')
        assert radio_val == 'NON_MEMBER'
        assert extra is None

    def test_empty_input_defaults_to_no_member(self):
        page = _parse(_MEMBER_RADIO_HTML)
        with patch('builtins.input', return_value=''):
            radio_val, extra = _select_member_radio(page, 'A123456789')
        assert radio_val == 'NON_MEMBER'
        assert extra is None

    def test_use_member_returns_member_value_and_extra_fields(self):
        page = _parse(_MEMBER_RADIO_HTML)
        with patch('builtins.input', return_value='y'):
            radio_val, extra = _select_member_radio(page, 'A123456789')
        assert radio_val == 'MEMBER'
        assert extra is not None

        radio_name = (
            'TicketMemberSystemInputPanel:TakerMemberSystemDataView:memberSystemRadioGroup'
        )
        assert extra[f'{radio_name}:memberShipNumber'] == 'A123456789'
        assert extra[f'{radio_name}:memberSystemShipCheckBox'] == 'on'

    def test_use_member_extra_has_exactly_two_keys(self):
        page = _parse(_MEMBER_RADIO_HTML)
        with patch('builtins.input', return_value='y'):
            _, extra = _select_member_radio(page, 'A123456789')
        assert len(extra) == 2


# ---------------------------------------------------------------------------
# _process_early_bird
# ---------------------------------------------------------------------------

class TestProcessEarlyBird:
    def test_no_early_bird_returns_none(self):
        page = _parse(_NO_EARLY_BIRD_HTML)
        result = _process_early_bird(page, 'A123456789')
        assert result is None

    def test_single_passenger_uses_personal_id_as_default(self):
        page = _parse(_EARLY_BIRD_1P_HTML)
        with patch('builtins.input', return_value=''):  # press Enter → use default
            result = _process_early_bird(page, 'A123456789')
        assert result is not None
        assert result[
            'TicketPassengerInfoInputPanel:passengerDataView:0'
            ':passengerDataView2:passengerDataIdNumber'
        ] == 'A123456789'

    def test_single_passenger_accepts_override_id(self):
        page = _parse(_EARLY_BIRD_1P_HTML)
        with patch('builtins.input', return_value='B987654321'):
            result = _process_early_bird(page, 'A123456789')
        assert result[
            'TicketPassengerInfoInputPanel:passengerDataView:0'
            ':passengerDataView2:passengerDataIdNumber'
        ] == 'B987654321'

    def test_single_passenger_early_type_propagated(self):
        page = _parse(_EARLY_BIRD_1P_HTML)
        with patch('builtins.input', return_value=''):
            result = _process_early_bird(page, 'A123456789')
        assert result[
            'TicketPassengerInfoInputPanel:passengerDataView:0'
            ':passengerDataView2:passengerDataTypeName'
        ] == 'EARLY_TYPE_A'

    def test_single_passenger_returns_five_fields(self):
        page = _parse(_EARLY_BIRD_1P_HTML)
        with patch('builtins.input', return_value=''):
            result = _process_early_bird(page, 'A123456789')
        assert len(result) == 5

    def test_two_passengers_second_id_required(self):
        page = _parse(_EARLY_BIRD_2P_HTML)
        # passenger 0: default, passenger 1: provide ID
        with patch('builtins.input', side_effect=['', 'C111222333']):
            result = _process_early_bird(page, 'A123456789')
        assert result[
            'TicketPassengerInfoInputPanel:passengerDataView:1'
            ':passengerDataView2:passengerDataIdNumber'
        ] == 'C111222333'

    def test_two_passengers_retries_until_non_empty(self):
        page = _parse(_EARLY_BIRD_2P_HTML)
        # passenger 1 submits empty twice then a valid ID
        with patch('builtins.input', side_effect=['', '', '', 'C111222333']):
            result = _process_early_bird(page, 'A123456789')
        assert result[
            'TicketPassengerInfoInputPanel:passengerDataView:1'
            ':passengerDataView2:passengerDataIdNumber'
        ] == 'C111222333'

    def test_two_passengers_returns_ten_fields(self):
        page = _parse(_EARLY_BIRD_2P_HTML)
        with patch('builtins.input', side_effect=['', 'C111222333']):
            result = _process_early_bird(page, 'A123456789')
        assert len(result) == 10


# ---------------------------------------------------------------------------
# ConfirmTicketFlow.run()
# ---------------------------------------------------------------------------

def _make_flow(html: str, personal_id: str = 'A123456789', phone: str = '0912345678'):
    """Return a ConfirmTicketFlow with a mocked client and a fake train response."""
    mock_resp = MagicMock()
    mock_resp.content = html.encode()

    mock_client = MagicMock()
    mock_client.submit_ticket.return_value = MagicMock()

    flow = ConfirmTicketFlow(client=mock_client, train_resp=mock_resp)
    return flow, mock_client


class TestConfirmTicketFlowRun:
    def test_no_membership_no_early_bird_submits_base_params(self):
        flow, mock_client = _make_flow(_FULL_PAGE_HTML)
        with patch('builtins.input', side_effect=[
            'A123456789',  # personal_id
            'n',           # use membership?
            '0912345678',  # phone
        ]):
            flow.run()

        submitted = mock_client.submit_ticket.call_args[0][0]
        assert submitted['dummyId'] == 'A123456789'
        assert submitted['dummyPhone'] == '0912345678'
        assert submitted[
            'TicketMemberSystemInputPanel:TakerMemberSystemDataView:memberSystemRadioGroup'
        ] == 'NON_MEMBER'
        # no membership or early-bird keys
        assert not any('memberShipNumber' in k for k in submitted)
        assert not any('passengerDataView' in k for k in submitted)

    def test_with_membership_adds_membership_fields(self):
        flow, mock_client = _make_flow(_FULL_PAGE_HTML)
        with patch('builtins.input', side_effect=[
            'A123456789',
            'y',           # use membership
            '0912345678',
        ]):
            flow.run()

        submitted = mock_client.submit_ticket.call_args[0][0]
        assert submitted[
            'TicketMemberSystemInputPanel:TakerMemberSystemDataView:memberSystemRadioGroup'
        ] == 'MEMBER'
        radio_name = (
            'TicketMemberSystemInputPanel:TakerMemberSystemDataView:memberSystemRadioGroup'
        )
        assert submitted[f'{radio_name}:memberShipNumber'] == 'A123456789'
        assert submitted[f'{radio_name}:memberSystemShipCheckBox'] == 'on'

    def test_with_early_bird_adds_passenger_fields(self):
        flow, mock_client = _make_flow(_EARLY_BIRD_1P_HTML + _MEMBER_RADIO_HTML)
        with patch('builtins.input', side_effect=[
            'A123456789',  # personal_id
            'n',           # use membership?
            '0912345678',  # phone
            '',            # passenger 0 ID → default
        ]):
            flow.run()

        submitted = mock_client.submit_ticket.call_args[0][0]
        assert submitted[
            'TicketPassengerInfoInputPanel:passengerDataView:0'
            ':passengerDataView2:passengerDataIdNumber'
        ] == 'A123456789'

    def test_run_returns_response_and_model(self):
        flow, mock_client = _make_flow(_FULL_PAGE_HTML)
        with patch('builtins.input', side_effect=[
            'A123456789',
            'n',
            '0912345678',
        ]):
            resp, model = flow.run()

        assert resp is mock_client.submit_ticket.return_value
        assert model.personal_id == 'A123456789'
