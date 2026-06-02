from typing import Any, Dict, List


def strategy_signature(ticker: str, expiration_date: str, legs: List[Dict[str, Any]]) -> str:
    """
    Produce a stable signature string for a strategy for matching/display.
    Example: "AAPL|20251219|BUY*1*150*C;SELL*1*155*C"
    """
    norm_legs = [
        {
            "action": str(l.get("action", "")).upper(),
            "quantity": int(l.get("quantity", 1)),
            "strike": float(l.get("strike")),
            "right": str(l.get("right", "")).upper(),
        }
        for l in legs
    ]
    norm_legs.sort(key=lambda x: (x["right"], x["strike"], x["action"]))
    parts = [f"{x['action']}*{x['quantity']}*{x['strike']}*{x['right']}" for x in norm_legs]
    return f"{str(ticker or '').upper()}|{expiration_date}|"+";".join(parts)


def normalize_open_strategy_signature_parts(legs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Normalize open position legs in the frontend-like shape:
    expects `position` to indicate BUY/SELL direction.
    """
    active_legs = [l for l in legs or [] if l.get("position") is not None and int(float(l.get("position"))) != 0]
    if not active_legs:
        return []

    # Normalize by gcd of absolute leg quantities to match JS behavior.
    # We keep this helper minimal; caller can decide whether to use it or just pass through legs.
    qtys = [abs(int(float(l.get("position")))) for l in active_legs]
    g = 0
    for q in qtys:
        g = q if g == 0 else __import__("math").gcd(g, q)
    g = g or 1

    out: List[Dict[str, Any]] = []
    for l in active_legs:
        out.append(
            {
                "action": "BUY" if float(l.get("position")) > 0 else "SELL",
                "quantity": abs(int(float(l.get("position")))) // g,
                "strike": float(l.get("strike")),
                "right": str(l.get("right", "")).upper()[:1],
            }
        )
    out.sort(key=lambda x: (x["right"], x["strike"], x["action"]))
    return out

