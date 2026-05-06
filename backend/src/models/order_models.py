from pydantic import BaseModel, root_validator
from typing import Any, Dict, List, Literal, Optional


def _normalize_leg_action(value: Any) -> str:
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError("'action' is required; use 'BUY' or 'SELL'")
    if not isinstance(value, str):
        raise ValueError("'action' must be a string (e.g. 'BUY' or 'SELL')")
    normalized = value.strip().upper()
    if normalized not in ("BUY", "SELL"):
        raise ValueError(
            f"Invalid leg action {value!r}; expected 'BUY' or 'SELL' (case-insensitive)"
        )
    return normalized


def _normalize_option_right(value: Any) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(
            "'right' must be a string (e.g. 'C', 'P', 'Call', or 'Put')"
        )
    s = value.strip()
    if len(s) == 1:
        u = s.upper()
        if u in ("C", "P"):
            return u
    low = s.lower()
    if low == "call":
        return "C"
    if low == "put":
        return "P"
    raise ValueError(
        f"Invalid option right {value!r}; use 'C', 'P', 'Call', or 'Put'"
    )


class OrderLeg(BaseModel):
    secType: Literal['STK', 'OPT'] = 'OPT'
    action: str  # 'BUY' or 'SELL'
    strike: Optional[float] = None
    right: Optional[Literal['C', 'P']] = None
    expiry: Optional[str] = None # YYYY-MM-DD

    @root_validator(pre=True)
    def normalize_leg_strings(cls, values):
        if not isinstance(values, dict):
            return values
        out = dict(values)
        if "action" in out:
            out["action"] = _normalize_leg_action(out["action"])
        if "right" in out and out.get("right") is not None:
            out["right"] = _normalize_option_right(out["right"])
        return out

    @root_validator(skip_on_failure=True)
    def check_leg_type_consistency(cls, values):
        secType = values.get('secType')
        strike = values.get('strike')
        right = values.get('right')
        expiry = values.get('expiry')

        if secType == 'OPT':
            if strike is None:
                raise ValueError("'strike' is required for option legs")
            if right is None:
                raise ValueError("'right' is required for option legs")
            if expiry is None:
                raise ValueError("'expiry' is required for option legs")
        elif secType == 'STK':
            if strike is not None:
                raise ValueError("'strike' must not be provided for stock legs")
            if right is not None:
                raise ValueError("'right' must not be provided for stock legs")
            if expiry is not None:
                raise ValueError("'expiry' must not be provided for stock legs")
        return values

class StrategyOrderRequest(BaseModel):
    ticker: str
    expiration_date: str # YYYY-MM-DD
    legs: List[OrderLeg]
    size: int = 1
    is_credit_spread: bool = False
    gpt_insights: Optional[Dict[str, Any]] = None  # GPT verdict insights for enhanced order context

    @root_validator(pre=True)
    def propagate_expiration_to_legs(cls, values):
        """
        If an expiration_date is provided at the strategy level, propagate it
        to all option legs that don't have their own expiry set. This ensures
        downstream functions receive a consistent `expiry` field on each leg.
        """
        expiration_date = values.get('expiration_date')
        if expiration_date:
            legs = values.get('legs', [])
            for leg in legs:
                # leg is a dict here because this is a pre-validator
                if isinstance(leg, dict):
                    # Default to OPT if secType is not specified
                    is_option = leg.get('secType', 'OPT') == 'OPT'
                    if is_option and not leg.get('expiry'):
                        leg['expiry'] = expiration_date
        return values
