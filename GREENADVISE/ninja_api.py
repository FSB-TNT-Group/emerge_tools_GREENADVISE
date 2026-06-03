"""
GREENADVISE V1.2 - Renewables.ninja API client
Fetches PV, wind, and temperature data for optimization inputs.

Results are cached to disk (core/ninja_cache/) so the same
location/year/capacity is never fetched more than once.
"""

import os
import re
import hashlib
import time

import requests
import numpy as np
import pandas as pd

BASE_URL = "https://www.renewables.ninja/api"

# Renewables.ninja rate limit: burst 1 req/sec, sustained 50 req/hour
_REQUEST_DELAY = 2.0   # seconds between consecutive API calls

# ── Cache directory (next to this file) ──────────────────────────────────────
_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ninja_cache")


def _ensure_cache_dir():
    os.makedirs(_CACHE_DIR, exist_ok=True)


def _cache_key(*parts) -> str:
    """Build a safe filename from arbitrary parts."""
    raw = "_".join(str(p) for p in parts)
    # replace characters that are unsafe on Windows/Linux
    safe = re.sub(r'[^A-Za-z0-9_\-\.]', '_', raw)
    # if very long, hash the tail
    if len(safe) > 180:
        h = hashlib.md5(safe.encode()).hexdigest()[:12]
        safe = safe[:160] + "_" + h
    return safe


def _cache_load(key: str):
    """Return cached array or None if not found."""
    path = os.path.join(_CACHE_DIR, key + ".npy")
    if os.path.isfile(path):
        return np.load(path)
    return None


def _cache_save(key: str, arr: np.ndarray):
    _ensure_cache_dir()
    np.save(os.path.join(_CACHE_DIR, key + ".npy"), arr)


# ── HTTP wrapper with rate-limit handling ─────────────────────────────────────

def _ninja_get(url, headers, params, label="API"):
    """
    Wrapper around requests.get that handles rate limiting (429) with a
    clear error message showing how long to wait.
    """
    time.sleep(_REQUEST_DELAY)   # always wait before each call
    r = requests.get(url, headers=headers, params=params, timeout=60)

    if r.status_code == 429:
        try:
            detail = r.json()
        except Exception:
            detail = r.text[:300]
        msg = str(detail)
        m = re.search(r"(\d+)\s*seconds?", msg)
        wait_secs = int(m.group(1)) if m else None
        wait_str = (
            f" Please wait {wait_secs // 60} min {wait_secs % 60} sec."
            if wait_secs else " Please wait before retrying."
        )
        raise requests.HTTPError(
            f"Renewables.ninja rate limit reached.{wait_str}\n"
            f"Detail: {detail}",
            response=r,
        )

    if r.status_code == 403:
        raise requests.HTTPError(
            f"403 Forbidden from Renewables.ninja.\n"
            f"Your API token may have been revoked or your IP may be temporarily "
            f"blocked. Please log in at renewables.ninja, verify your account, "
            f"and copy a fresh API token.",
            response=r,
        )

    if r.status_code == 401:
        raise requests.HTTPError(
            f"401 Unauthorized from Renewables.ninja.\n"
            f"Your API token is invalid. Please check the token in the app settings.",
            response=r,
        )

    if not r.ok:
        try:
            detail = r.json()
        except Exception:
            detail = r.text[:300]
        raise requests.HTTPError(
            f"{r.status_code} from Renewables.ninja {label}: {detail}",
            response=r,
        )

    return r


# ── Public fetch functions ────────────────────────────────────────────────────

def fetch_pv(api_key, lat, lon, year,
             capacity_kw=1.0, tracking=0, tilt=35, azimuth=180, system_loss=0.1):
    """
    Fetch hourly PV generation from Renewables.ninja (cached).

    Returns
    -------
    numpy.ndarray, shape (8760,)
        Hourly electricity output in kWh.
    """
    lat  = round(float(lat), 6)
    lon  = round(float(lon), 6)
    tilt = int(round(float(tilt)))
    azim = int(round(float(azimuth)))

    key = _cache_key("pv", lat, lon, year,
                     capacity_kw, tracking, tilt, azim, system_loss)
    cached = _cache_load(key)
    if cached is not None:
        return cached

    headers = {"Authorization": f"Token {api_key}"}
    params = {
        "lat":         lat,
        "lon":         lon,
        "date_from":   f"{int(year)}-01-01",
        "date_to":     f"{int(year)}-12-31",
        "dataset":     "merra2",
        "capacity":    float(capacity_kw),
        "system_loss": float(system_loss),
        "tracking":    int(tracking),
        "tilt":        tilt,
        "azim":        azim,
        "format":      "json",
    }
    r    = _ninja_get(f"{BASE_URL}/data/pv", headers, params, label="PV")
    data = r.json()
    df   = pd.DataFrame.from_dict(data["data"], orient="index")
    arr  = df["electricity"].values
    if len(arr) < 8760:
        arr = np.pad(arr, (0, 8760 - len(arr)), constant_values=0)
    arr = arr[:8760].astype(float)
    _cache_save(key, arr)
    return arr


def fetch_wind(api_key, lat, lon, year,
               capacity_kw=1.0, hub_height=80, turbine="Vestas V80 2000"):
    """
    Fetch hourly wind generation from Renewables.ninja (cached).

    Returns
    -------
    numpy.ndarray, shape (8760,)
        Hourly electricity output in kWh.
    """
    lat = round(float(lat), 6)
    lon = round(float(lon), 6)

    key = _cache_key("wind", lat, lon, year, capacity_kw, hub_height, turbine)
    cached = _cache_load(key)
    if cached is not None:
        return cached

    headers = {"Authorization": f"Token {api_key}"}
    params = {
        "lat":       lat,
        "lon":       lon,
        "date_from": f"{int(year)}-01-01",
        "date_to":   f"{int(year)}-12-31",
        "dataset":   "merra2",
        "capacity":  float(capacity_kw),
        "height":    int(round(float(hub_height))),
        "turbine":   turbine,
        "format":    "json",
    }
    r    = _ninja_get(f"{BASE_URL}/data/wind", headers, params, label="Wind")
    data = r.json()
    df   = pd.DataFrame.from_dict(data["data"], orient="index")
    arr  = df["electricity"].values
    if len(arr) < 8760:
        arr = np.pad(arr, (0, 8760 - len(arr)), constant_values=0)
    arr = arr[:8760].astype(float)
    _cache_save(key, arr)
    return arr


def fetch_temperature(api_key, lat, lon, year):
    """
    Fetch hourly ambient temperature from Renewables.ninja (cached).

    Returns
    -------
    numpy.ndarray, shape (8760,)
        Hourly temperature in °C (zeros if unavailable).
    """
    lat = round(float(lat), 6)
    lon = round(float(lon), 6)

    key = _cache_key("temp", lat, lon, year)
    cached = _cache_load(key)
    if cached is not None:
        return cached

    headers = {"Authorization": f"Token {api_key}"}
    params = {
        "lat":         lat,
        "lon":         lon,
        "date_from":   f"{int(year)}-01-01",
        "date_to":     f"{int(year)}-12-31",
        "dataset":     "merra2",
        "capacity":    1,
        "system_loss": 0,
        "tracking":    0,
        "tilt":        35,
        "azim":        180,
        "format":      "json",
    }
    r    = _ninja_get(f"{BASE_URL}/data/pv", headers, params, label="Temp")
    data = r.json()
    df   = pd.DataFrame.from_dict(data["data"], orient="index")
    if "temperature" in df.columns:
        arr = df["temperature"].values.astype(float)
    else:
        arr = np.zeros(8760)
    if len(arr) < 8760:
        arr = np.pad(arr, (0, 8760 - len(arr)), constant_values=0)
    arr = arr[:8760]
    _cache_save(key, arr)
    return arr


def fetch_all_historical_years(
    api_key, lat, lon, pv_capacity, wind_capacity,
    hub_height=80, turbine="Vestas V80 2000",
    pv_tracking=0, pv_tilt=35, pv_azimuth=180,
    progress_callback=None,
    max_years=20,
):
    """
    Fetch recent historical years from Renewables.ninja for LSTM-VAE training.
    Uses the most recent `max_years` years (default 20: 2003-2022).
    Cached results skip the API entirely.

    Returns
    -------
    list of dict, each with keys:
        'year' : int
        'pv'   : np.ndarray shape (8760,)
        'wind' : np.ndarray shape (8760,)
        'temp' : np.ndarray shape (8760,)
    """
    all_years = list(range(2000, 2023))
    available_years = all_years[-max_years:]   # most recent N years
    historical = []

    for year in available_years:
        try:
            if progress_callback:
                progress_callback(f"Fetching historical year {year}...")

            scen = {"year": year}

            if pv_capacity > 0:
                scen["pv"] = fetch_pv(
                    api_key, lat, lon, year,
                    capacity_kw=pv_capacity,
                    tracking=pv_tracking,
                    tilt=pv_tilt,
                    azimuth=pv_azimuth,
                )
            else:
                scen["pv"] = np.zeros(8760)

            if wind_capacity > 0:
                scen["wind"] = fetch_wind(
                    api_key, lat, lon, year,
                    capacity_kw=wind_capacity,
                    hub_height=hub_height,
                    turbine=turbine,
                )
            else:
                scen["wind"] = np.zeros(8760)

            # Temperature is optional: used only for diurnal profiles, not for
            # the optimization itself. A failed fetch uses zeros and does not
            # skip the year.
            try:
                scen["temp"] = fetch_temperature(api_key, lat, lon, year)
            except Exception:
                scen["temp"] = np.zeros(8760)

            historical.append(scen)

        except requests.HTTPError as e:
            msg = str(e)
            if "rate limit" in msg.lower() or "429" in msg:
                # Stop immediately and re-raise: no point trying more years
                raise requests.HTTPError(
                    f"Renewables.ninja rate limit reached while fetching year {year}.\n"
                    f"{msg}",
                    response=e.response,
                )
            if progress_callback:
                progress_callback(f"  Skipped year {year}: {e}")
        except Exception as e:
            if progress_callback:
                progress_callback(f"  Skipped year {year}: {e}")

    if progress_callback:
        progress_callback(f"Fetched {len(historical)} historical years.")
    return historical


def fetch_scenarios(api_key, lat, lon, n_scenarios, pv_capacity, wind_capacity,
                    hub_height=80, turbine="Vestas V80 2000",
                    pv_tracking=0, pv_tilt=35, pv_azimuth=180):
    """
    Fetch n_scenarios years of PV + wind data for stochastic optimization.
    Uses years 2010 … 2010+n_scenarios-1 from the MERRA-2 dataset.
    Cached results skip the API entirely.

    Returns
    -------
    list of dict, each with keys:
        'year'  : int
        'pv'    : np.ndarray shape (8760,)
        'wind'  : np.ndarray shape (8760,)
    """
    years     = list(range(2010, 2010 + n_scenarios))
    scenarios = []

    for year in years:
        scen = {"year": year}

        if pv_capacity > 0:
            scen["pv"] = fetch_pv(
                api_key, lat, lon, year,
                capacity_kw=pv_capacity,
                tracking=pv_tracking,
                tilt=pv_tilt,
                azimuth=pv_azimuth,
            )
        else:
            scen["pv"] = np.zeros(8760)

        if wind_capacity > 0:
            scen["wind"] = fetch_wind(
                api_key, lat, lon, year,
                capacity_kw=wind_capacity,
                hub_height=hub_height,
                turbine=turbine,
            )
        else:
            scen["wind"] = np.zeros(8760)

        scenarios.append(scen)

    return scenarios
