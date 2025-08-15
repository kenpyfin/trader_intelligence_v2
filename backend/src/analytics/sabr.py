import numpy as np
from math import log, sqrt
from scipy.optimize import minimize

def _hagan_implied_vol(F, K, T, alpha, beta, rho, nu):
    """
    Hagan et al. (2002) SABR implied vol approximation.
    F: forward
    K: strike
    T: time to maturity (in years)
    alpha, beta, rho, nu: SABR parameters
    """
    # Handle F == K separately (ATM formula)
    if F <= 0 or K <= 0 or T <= 0:
        return np.nan

    one_m_beta = 1.0 - beta
    FK = F * K
    logFK = log(F / K)

    # z and x(z)
    if abs(F - K) < 1e-12:
        # ATM case
        z = 0.0
        x_z = 1.0
    else:
        z = (nu / alpha) * (FK) ** (0.5 * one_m_beta) * logFK
        # x(z) function to reduce to ATM in the limit
        sqrt_term = sqrt(1 - 2 * rho * z + z * z)
        x_z = log((sqrt_term + z - rho) / (1 - rho))

        if abs(x_z) < 1e-12:
            # Avoid division by zero if x_z becomes extremely small
            x_z = 1e-12

    # Denominator term
    denom = (FK) ** (0.5 * one_m_beta) * (1 + (one_m_beta ** 2 / 24.0) * (logFK ** 2) + (one_m_beta ** 4 / 1920.0) * (logFK ** 4))

    # ATM correction factor
    A = alpha / denom

    # z/x(z) factor
    if abs(z) < 1e-12:
        B = 1.0
    else:
        B = z / x_z

    # D(T) time-dependent correction
    term1 = ((one_m_beta ** 2) / 24.0) * (alpha ** 2) / ( (FK) ** (one_m_beta) )
    term2 = (rho * beta * nu * alpha) / (4.0 * (FK) ** (0.5 * one_m_beta))
    term3 = ((2.0 - 3.0 * rho * rho) / 24.0) * (nu ** 2)
    D = 1.0 + (term1 + term2 + term3) * T

    return float(A * B * D)


def sabr_iv(F, K, T, alpha, beta, rho, nu):
    """
    Public wrapper returning a positive volatility with simple guards.
    """
    iv = _hagan_implied_vol(F, K, T, alpha, beta, rho, nu)
    if iv is None or np.isnan(iv) or iv <= 0:
        return np.nan
    return iv


def calibrate_sabr(F, strikes, market_ivs, T, beta_init=0.9):
    """
    Calibrate SABR parameters (alpha, beta, rho, nu) to market IVs using least squares.

    Args:
        F (float): forward price
        strikes (np.ndarray): array of strikes
        market_ivs (np.ndarray): array of market implied vols at the strikes (as decimals)
        T (float): time to maturity in years
        beta_init (float): initial beta (0 < beta <= 1)

    Returns:
        tuple: (alpha, beta, rho, nu)
    """
    strikes = np.asarray(strikes, dtype=float)
    market_ivs = np.asarray(market_ivs, dtype=float)

    # Initial guesses
    # Rough alpha guess using ATM (closest strike) if available
    idx_atm = np.argmin(np.abs(strikes - F))
    iv_atm = float(market_ivs[idx_atm]) if len(market_ivs) > 0 else float(np.nan)
    beta0 = float(np.clip(beta_init, 0.3, 1.0))
    # guard F**(1-beta)
    denom = max(F ** (1.0 - beta0), 1e-8)
    alpha0 = max(iv_atm * denom if np.isfinite(iv_atm) and iv_atm > 0 else 0.2 * denom, 1e-6)
    rho0 = 0.0
    nu0 = 0.5

    x0 = np.array([alpha0, beta0, rho0, nu0], dtype=float)

    bounds = [
        (1e-8, 5.0),   # alpha
        (0.3, 1.0),    # beta
        (-0.999, 0.999), # rho
        (1e-8, 5.0)    # nu
    ]

    def objective(x):
        a, b, r, n = x
        fitted = np.array([sabr_iv(F, k, T, a, b, r, n) for k in strikes])
        # Penalize NaNs and negative values heavily
        if np.any(~np.isfinite(fitted)) or np.any(fitted <= 0):
            return 1e6
        err = market_ivs - fitted
        # RMSE
        return np.sqrt(np.mean(err * err))

    res = minimize(objective, x0, method='L-BFGS-B', bounds=bounds, options={'maxiter': 200})
    if not res.success:
        # Fallback: try with different beta
        for beta0_alt in [0.7, 0.8, 0.95]:
            x0_alt = np.array([alpha0, beta0_alt, rho0, nu0], dtype=float)
            res_alt = minimize(objective, x0_alt, method='L-BFGS-B', bounds=bounds, options={'maxiter': 200})
            if res_alt.success:
                return tuple(res_alt.x)

    return tuple(res.x if res.success else x0)
