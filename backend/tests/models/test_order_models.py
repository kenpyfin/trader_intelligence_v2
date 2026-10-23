"""Tests for strategy order request / leg validation and normalization."""

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

BACKEND_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = BACKEND_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from models.order_models import OrderLeg, StrategyOrderRequest


class TestOrderLegNormalization:
    def test_action_buy_sell_case_insensitive(self):
        leg = OrderLeg(action="buy", strike=100.0, right="C", expiry="2026-06-05")
        assert leg.action == "BUY"
        leg2 = OrderLeg(action="  sell ", strike=100.0, right="P", expiry="2026-06-05")
        assert leg2.action == "SELL"

    def test_right_call_put_aliases(self):
        leg = OrderLeg(action="BUY", strike=390.0, right="Call", expiry="2026-06-05")
        assert leg.right == "C"
        leg2 = OrderLeg(action="BUY", strike=390.0, right="put", expiry="2026-06-05")
        assert leg2.right == "P"
        leg3 = OrderLeg(action="BUY", strike=390.0, right="c", expiry="2026-06-05")
        assert leg3.right == "C"

    def test_right_c_p_unchanged(self):
        leg = OrderLeg(action="BUY", strike=390.0, right="P", expiry="2026-06-05")
        assert leg.right == "P"

    def test_invalid_action_message(self):
        with pytest.raises(ValidationError) as exc:
            OrderLeg(action="HOLD", strike=100.0, right="C", expiry="2026-06-05")
        err = exc.value.errors()[0]
        assert "Invalid leg action" in err["msg"] or "BUY" in err["msg"]

    def test_invalid_right_message(self):
        with pytest.raises(ValidationError) as exc:
            OrderLeg(action="BUY", strike=100.0, right="CALLL", expiry="2026-06-05")
        err = exc.value.errors()[0]
        assert "Invalid option right" in err["msg"] or "Call" in err["msg"]


class TestStrategyOrderRequestGptStyleLegs:
    def test_full_request_with_call_put_and_propagated_expiry(self):
        req = StrategyOrderRequest(
            ticker="TSLA",
            expiration_date="2026-06-05",
            legs=[
                {
                    "action": "Buy",
                    "strike": 390,
                    "right": "Call",
                    "quantity": 1,
                },
                {
                    "action": "Sell",
                    "strike": 440,
                    "right": "Call",
                    "quantity": 1,
                },
            ],
            is_credit_spread=False,
        )
        assert len(req.legs) == 2
        assert req.legs[0].right == "C"
        assert req.legs[0].expiry == "2026-06-05"
        assert req.legs[1].action == "SELL"
        assert req.legs[1].right == "C"
        assert req.legs[1].expiry == "2026-06-05"
