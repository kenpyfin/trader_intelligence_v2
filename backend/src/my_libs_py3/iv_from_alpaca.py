"""
Compute IV points (7d / 30d / 90d and spot) from Alpaca option chain + spot.

Alpaca does not provide implied volatility directly; we back it out from
option prices (bid/ask mid or last) using the binomial pricer (American-style).
Used by the IV pipeline so the same data can be saved to MongoDB for IV rank.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from .pyfin import Option, OptionType, OptionExerciseType


def _parse_occ_symbol(occ: str) -> Dict[str, Any]:
    """Parse OCC option symbol to underlying, expiry (YYYYMMDD), right, strike."""
    if not occ or len(occ) < 15:
        return {}
    cleaned = occ.replace(" ", "")
    first_digit = next((i for i, c in enumerate(cleaned) if c.isdigit()), None)
    if first_digit is None or len(cleaned) < first_digit + 15:
        return {}
    expiry_seg = cleaned[first_digit : first_digit + 6]
    right = (cleaned[first_digit + 6] or "").upper()
    strike_seg = cleaned[first_digit + 7 : first_digit + 15]
    try:
        strike = int(strike_seg) / 1000.0
    except ValueError:
        return {}
    if not expiry_seg.isdigit():
        return {}
    y, m, d = expiry_seg[:2], expiry_seg[2:4], expiry_seg[4:6]
    expiry = f"20{y}{m}{d}"
    return {"expiry": expiry, "right": right, "strike": strike}


def _mid_from_snapshot(snapshot: Any) -> Optional[float]:
    """Extract mid price from Alpaca option snapshot (quote mid or bid/ask average, else last trade)."""
    quote = getattr(snapshot, "latest_quote", None)
    trade = getattr(snapshot, "latest_trade", None)
    bid = getattr(quote, "bid_price", None) if quote else None
    ask = getattr(quote, "ask_price", None) if quote else None
    mid = getattr(quote, "midpoint", None) if quote else None
    if mid is not None:
        try:
            return float(mid)
        except (TypeError, ValueError):
            pass
    if bid is not None and ask is not None:
        try:
            return (float(bid) + float(ask)) / 2.0
        except (TypeError, ValueError):
            pass
    if trade is not None:
        p = getattr(trade, "price", None)
        if p is not None:
            try:
                return float(p)
            except (TypeError, ValueError):
                pass
    return None


def _chain_to_rows_by_expiry(chain_dict: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """Convert Alpaca chain (occ -> snapshot) to expiry -> list of {strike, type, mid}."""
    by_expiry: Dict[str, List[Dict[str, Any]]] = {}
    for occ, snapshot in (chain_dict or {}).items():
        parsed = _parse_occ_symbol(occ)
        if not parsed or not parsed.get("expiry"):
            continue
        mid = _mid_from_snapshot(snapshot)
        if mid is None or mid <= 0:
            continue
        expiry = parsed["expiry"]
        row = {
            "strike": parsed["strike"],
            "type": "call" if parsed.get("right") == "C" else "put",
            "mid": mid,
        }
        by_expiry.setdefault(expiry, []).append(row)
    return by_expiry


def _expiry_to_dte(expiry_yyyymmdd: str, ref: date) -> int:
    """Return days from ref to expiry (expiry is YYYYMMDD string)."""
    try:
        y, m, d = int(expiry_yyyymmdd[:4]), int(expiry_yyyymmdd[4:6]), int(expiry_yyyymmdd[6:8])
        exp = date(y, m, d)
        return (exp - ref).days
    except (ValueError, IndexError):
        return 9999


def _pick_expiry_for_dte(by_expiry: Dict[str, List], target_dte: int, ref: date) -> Optional[str]:
    """Return expiry key (YYYYMMDD) whose DTE is closest to target_dte (legacy)."""
    best_key: Optional[str] = None
    best_diff = 9999
    for exp_key in by_expiry:
        dte = _expiry_to_dte(exp_key, ref)
        if dte < 0:
            continue
        diff = abs(dte - target_dte)
        if diff < best_diff:
            best_diff = diff
            best_key = exp_key
    return best_key


def _pick_expiry_at_least_dte(by_expiry: Dict[str, List], min_dte: int, ref: date) -> Optional[str]:
    """Return expiry key (YYYYMMDD) with the smallest DTE among those with DTE >= min_dte."""
    best_key: Optional[str] = None
    best_dte = 9999
    for exp_key in by_expiry:
        dte = _expiry_to_dte(exp_key, ref)
        if dte < min_dte:
            continue
        if dte < best_dte:
            best_dte = dte
            best_key = exp_key
    return best_key


def _atm_mid_for_expiry(rows: List[Dict[str, Any]], spot: float) -> Optional[Tuple[float, float, str]]:
    """Return (strike, mid_price, option_type) for ATM option. Prefer call."""
    if not rows or spot <= 0:
        return None
    by_strike: Dict[float, Dict[str, Any]] = {}
    for r in rows:
        k = r.get("strike")
        if k is None:
            continue
        by_strike.setdefault(k, {}).update(r)
    strikes = sorted(by_strike.keys())
    atm_strike = min(strikes, key=lambda s: abs(s - spot))
    # Prefer call then put for same strike
    for opt_type in ("call", "put"):
        for r in rows:
            if r.get("strike") == atm_strike and (r.get("type") or "").lower() == opt_type:
                mid = r.get("mid")
                if mid is not None and mid > 0:
                    return (atm_strike, mid, opt_type)
    return None


def _mat_years(expiry_yyyymmdd: str, ref: date) -> float:
    """Time to expiry in years."""
    dte = _expiry_to_dte(expiry_yyyymmdd, ref)
    return max(dte / 365.0, 1.0 / 365.0)


def _imply_vol(premium: float, spot: float, strike: float, mat_years: float, option_type: str, risk_free: float = 0.05) -> Optional[float]:
    """Back out IV from option premium using American binomial model."""
    if premium <= 0 or spot <= 0 or strike <= 0 or mat_years <= 0:
        return None
    opt_type = OptionType.CALL if (option_type or "call").lower() == "call" else OptionType.PUT
    try:
        iv = Option.imply_volatility(
            premium,
            max_vol=0.99,
            opt_type=opt_type,
            spot0=spot,
            strike=strike,
            mat=mat_years,
            riskless_rate=risk_free,
            yield_=0.0,
            exer_type=OptionExerciseType.AMERICAN,
        )
        return iv
    except Exception:
        return None


def calculate_iv_points_from_alpaca_chain(
    chain_dict: Dict[str, Any],
    spot: float,
    risk_free_rate: float = 0.05,
    target_dtes: Tuple[int, ...] = (7, 30, 90),
    ref_date: Optional[date] = None,
) -> Optional[Dict[str, float]]:
    """
    Compute IV points from Alpaca option chain (occ_symbol -> snapshot) and spot.

    Returns dict with keys "spot", "7d", "30d", "90d" (or only those tenors that
    could be computed). "spot" is set to the shortest available tenor (e.g. 7d)
    for use as spot_iv in MongoDB iv_history. The pipeline (e.g. collect_iv_history
    in My_Trader2.0) can save this as-is; calculate_iv_rank() in trader intelligence
    reads spot_iv from iv_history.
    """
    if not chain_dict or spot is None or spot <= 0:
        return None
    ref = ref_date or date.today()
    by_expiry = _chain_to_rows_by_expiry(chain_dict)
    if not by_expiry:
        return None

    result: Dict[str, float] = {}
    for min_dte in target_dtes:
        label = f"{min_dte}d"
        exp_key = _pick_expiry_at_least_dte(by_expiry, min_dte, ref)
        if not exp_key:
            continue
        rows = by_expiry.get(exp_key, [])
        atm = _atm_mid_for_expiry(rows, spot)
        if not atm:
            continue
        strike, mid, opt_type = atm
        mat_years = _mat_years(exp_key, ref)
        iv = _imply_vol(mid, spot, strike, mat_years, opt_type, risk_free_rate)
        if iv is not None and 0.01 <= iv <= 0.99:
            result[label] = iv

    if not result:
        return None
    # spot_iv = shortest available (7d preferred, else first we have)
    for key in ("7d", "30d", "90d"):
        if key in result:
            result["spot"] = result[key]
            break
    return result
