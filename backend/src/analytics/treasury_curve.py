from datetime import date, timedelta
import numpy as np
from typing import Callable, Dict, List, Tuple

def _extract_yield_points(record: dict) -> List[Tuple[float, float]]:
    """
    Convert an FMP treasury record into (maturity_in_years, rate_decimal) points.
    Ignores missing values.
    """
    mapping = {
        'month1': 1/12, 'month3': 3/12, 'month6': 6/12,
        'year1': 1.0, 'year2': 2.0, 'year3': 3.0, 'year5': 5.0,
        'year7': 7.0, 'year10': 10.0, 'year20': 20.0, 'year30': 30.0
    }
    points = []
    for key, T in mapping.items():
        if key in record and record[key] is not None:
            try:
                r = float(record[key]) / 100.0  # convert percent to decimal
                if np.isfinite(r):
                    points.append((float(T), r))
            except (TypeError, ValueError):
                continue
    points.sort(key=lambda x: x[0])
    return points

def build_treasury_curve(fmp_client, on_date: date = None) -> Dict[str, object]:
    """
    Builds a simple piecewise-linear zero-rate curve from FMP Treasury yields.
    Returns:
      {
        'as_of': 'YYYY-MM-DD',
        'terms': [(T_years, rate_decimal), ...]  # sorted by maturity
        'rate_fn': callable(T_years) -> rate_decimal
      }
    """
    if on_date is None:
        to_date = date.today()
        from_date = to_date - timedelta(days=10)
        df = fmp_client.get_treasury_yields(from_date=from_date.strftime('%Y-%m-%d'), to_date=to_date.strftime('%Y-%m-%d'))
        if df is None or df.empty:
            # Fallback: constant 4.5%
            return {
                'as_of': to_date.strftime('%Y-%m-%d'),
                'terms': [],
                'rate_fn': (lambda T: 0.045)
            }
        record = df.sort_values('date').iloc[-1].to_dict()
    else:
        df = fmp_client.get_treasury_yields(date=on_date.strftime('%Y-%m-%d'))
        if df is None or df.empty:
            return {
                'as_of': on_date.strftime('%Y-%m-%d'),
                'terms': [],
                'rate_fn': (lambda T: 0.045)
            }
        record = df.sort_values('date').iloc[-1].to_dict()

    points = _extract_yield_points(record)

    if not points:
        as_of = record.get('date') if 'date' in record else date.today().strftime('%Y-%m-%d')
        return {
            'as_of': as_of,
            'terms': [],
            'rate_fn': (lambda T: 0.045)
        }

    Ts = np.array([p[0] for p in points], dtype=float)
    Rs = np.array([p[1] for p in points], dtype=float)

    def rate_fn(T: float) -> float:
        if T <= Ts[0]:
            return float(Rs[0])
        if T >= Ts[-1]:
            return float(Rs[-1])
        # linear interpolation
        return float(np.interp(T, Ts, Rs))

    return {
        'as_of': str(record.get('date')),
        'terms': [(float(Ts[i]), float(Rs[i])) for i in range(len(Ts))],
        'rate_fn': rate_fn
    }
