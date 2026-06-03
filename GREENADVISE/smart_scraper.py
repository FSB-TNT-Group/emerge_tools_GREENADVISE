from __future__ import annotations
from typing import Dict, Any, Optional, Tuple
import hashlib, json
import numpy as np

from Scrape_from_Ninja import NinjaScraper


def _stable_key(kind: str, lat: float, lon: float, inputs: Optional[Dict[str, Any]]) -> str:
    payload = {
        "kind": kind,
        "lat": round(float(lat), 6),
        "lon": round(float(lon), 6),
        "inputs": inputs or {},
    }
    s = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


class SmartNinjaScraper:
    def __init__(self, api_key: str, lat: float, lon: float):
        self.api_key = api_key
        self.lat = float(lat)
        self.lon = float(lon)
        self._cache: Dict[str, Any] = {}

    def _call(self, *, pv_inputs=None, wind_inputs=None, temperature_inputs=None) -> Dict[str, Any]:
        ninja = NinjaScraper(
            api_key=self.api_key,
            lat=self.lat,
            lon=self.lon,
            pv_inputs=pv_inputs,
            wind_inputs=wind_inputs,
            temperature_inputs=temperature_inputs,
        )


        data: Dict[str, Any] = ninja.fetch()
        return data

    def fetch_pv(self, pv_inputs: Dict[str, Any]) -> np.ndarray:
        key = _stable_key("pv", self.lat, self.lon, pv_inputs)
        if key in self._cache:
            return self._cache[key]
        res = self._call(pv_inputs=pv_inputs)
        pv = res["pv"] if isinstance(res, dict) and "pv" in res else res
        self._cache[key] = pv
        return pv

    def fetch_wind(self, wind_inputs: Dict[str, Any]) -> np.ndarray:
        key = _stable_key("wind", self.lat, self.lon, wind_inputs)
        if key in self._cache:
            return self._cache[key]
        res = self._call(wind_inputs=wind_inputs)
        wind = res["wind"] if isinstance(res, dict) and "wind" in res else res
        self._cache[key] = wind
        return wind

    def fetch_temperature(self, temperature_inputs: Dict[str, Any]) -> np.ndarray:
        key = _stable_key("temperature", self.lat, self.lon, temperature_inputs)
        if key in self._cache:
            return self._cache[key]
        res = self._call(temperature_inputs=temperature_inputs)
        temp = res["temperature"] if isinstance(res, dict) and "temperature" in res else res
        self._cache[key] = temp
        return temp

    def fetch(self,
              *,
              pv_inputs: Optional[Dict[str, Any]] = None,
              wind_inputs: Optional[Dict[str, Any]] = None,
              temperature_inputs: Optional[Dict[str, Any]] = None
              ) -> Dict[str, Any]:
        out: Dict[str, Any] = {}

        requested = [pv_inputs is not None, wind_inputs is not None, temperature_inputs is not None]
        if sum(requested) == 1:
            if pv_inputs is not None:
                out["pv"] = self.fetch_pv(pv_inputs)
            elif wind_inputs is not None:
                out["wind"] = self.fetch_wind(wind_inputs)
            else:
                out["temperature"] = self.fetch_temperature(temperature_inputs)
            return out


        need_call = False
        combined_inputs = {"pv_inputs": None, "wind_inputs": None, "temperature_inputs": None}

        if pv_inputs is not None:
            k = _stable_key("pv", self.lat, self.lon, pv_inputs)
            if k in self._cache:
                out["pv"] = self._cache[k]
            else:
                combined_inputs["pv_inputs"] = pv_inputs
                need_call = True

        if wind_inputs is not None:
            k = _stable_key("wind", self.lat, self.lon, wind_inputs)
            if k in self._cache:
                out["wind"] = self._cache[k]
            else:
                combined_inputs["wind_inputs"] = wind_inputs
                need_call = True

        if temperature_inputs is not None:
            k = _stable_key("temperature", self.lat, self.lon, temperature_inputs)
            if k in self._cache:
                out["temperature"] = self._cache[k]
            else:
                combined_inputs["temperature_inputs"] = temperature_inputs
                need_call = True

        if need_call:
            res = self._call(**combined_inputs)
            if "pv" in res:
                ck = _stable_key("pv", self.lat, self.lon, pv_inputs)
                self._cache[ck] = res["pv"]
                out["pv"] = res["pv"]
            if "wind" in res:
                ck = _stable_key("wind", self.lat, self.lon, wind_inputs)
                self._cache[ck] = res["wind"]
                out["wind"] = res["wind"]
            if "temperature" in res:
                ck = _stable_key("temperature", self.lat, self.lon, temperature_inputs)
                self._cache[ck] = res["temperature"]
                out["temperature"] = res["temperature"]

        return out

    def clear_cache(self) -> None:
        self._cache.clear()

    @staticmethod
    def build_plan_from_selection(selected: Dict[str, Any],
                                  meta: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        plan: Dict[str, Dict[str, Any]] = {}

        if "PV Generation" in selected and "PV Generation" in meta:
            plan["pv"] = meta["PV Generation"]
        if "Wind Generation" in selected and "Wind Generation" in meta:
            plan["wind"] = meta["Wind Generation"]

        if "Thermal Demand" in selected and "Thermal Demand" in meta:
            plan["temperature"] = meta["Thermal Demand"]

        if "Thermal + Electricity Demand" in selected and "Thermal Demand" in meta:
            plan.setdefault("temperature", meta["Thermal Demand"])

        return plan
