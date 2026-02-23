from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
import requests


@dataclass
class SDSClient:
    base_url: str
    api_key: str
    timeout_s: int = 30
    sensor_cache: dict[str, dict[str, str]] = field(default_factory=dict[str, dict[str, str]])

    def _headers(self) -> dict[str, str]:
        # Per SDS manual: header name is exactly "apiKey"
        return {"apiKey": self.api_key}

    def _get(
        self, endpoint: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any] | list[dict[str, Any]]:  #  type: ignore[return]
        url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"

        # retry with backoff
        for attempt in range(1, 6):
            try:
                r = requests.get(
                    url, headers=self._headers(), params=params, timeout=self.timeout_s
                )
                r.raise_for_status()
                return r.json()
            except requests.exceptions.RequestException as e:
                sleep_s = min(2**attempt, 20)
                print(
                    f"[WARN] GET {endpoint} failed (attempt {attempt}/5): {e} | retry in {sleep_s}s"
                )
                time.sleep(sleep_s)

                if attempt == 5:
                    raise e

    # ---- Core endpoints ----

    def list_components(self) -> list[dict[str, Any]] | list[dict[str, Any]]:
        payload = self._get("components")
        if isinstance(payload, dict):
            return payload.get("components") or payload.get("data") or []
        return payload if isinstance(payload, list) else []  # type: ignore[return]

    def list_sensors(self, component_uuid: str) -> list[dict[str, Any]] | list[dict[str, Any]]:
        payload = self._get("sensors", params={"componentuuid": component_uuid})
        if isinstance(payload, dict):
            return payload.get("sensors") or payload.get("data") or []
        return payload if isinstance(payload, list) else []  # type: ignore[return]

    def list_incidents(
        self: SDSClient, status: str | None = None, component_uuid: str | None = None
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {}
        if status:
            params["status"] = status
        if component_uuid:
            params["componentuuid"] = component_uuid

        payload = self._get("incidents", params=params)
        if isinstance(payload, dict):
            return payload.get("incidents") or payload.get("data") or []
        return payload if isinstance(payload, list) else []  # type: ignore[return]

    def get_measurements(
        self,
        sensor_uuid: str,
        begin_epoch: int | None = None,
        end_epoch: int | None = None,
        timezone: str = "UTC",
        sampling: str = "P",
        value: int = 0,
        limit: int = 5000,
        # Backwards-compatible aliases:
        begin: int | None = None,
        end: int | None = None,
        begin_ts: int | None = None,
        end_ts: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Return measurements as a LIST always.
        Accepts begin/end in multiple naming conventions for compatibility.
        """

        b = begin_epoch if begin_epoch is not None else begin
        b = b if b is not None else begin_ts

        e = end_epoch if end_epoch is not None else end
        e = e if e is not None else end_ts

        if b is None or e is None:
            raise TypeError("get_measurements() requires begin/end epoch seconds")

        payload = self._get(
            "measurements",
            params={
                "sensoruuid": sensor_uuid,
                "begin": int(b),
                "end": int(e),
                "timezone": timezone,
                "sampling": sampling,
                "value": value,
                "limit": limit,
            },
        )

        if isinstance(payload, dict):
            return (
                payload.get("measurements") or payload.get("data") or payload.get("results") or []
            )
        return payload if isinstance(payload, list) else []  # type: ignore[return]

    # ---- Convenience helpers ----

    def get_latest_value(
        self, sensor_uuid: str, lookback_seconds: int = 24 * 3600
    ) -> dict[str, Any] | None:
        """
        Get the latest measurement for a sensor in the last lookback_seconds.
        Returns dict with value + timestamp, or None if no data.
        """
        end_ts = int(time.time())
        begin_ts = end_ts - int(lookback_seconds)

        series = self.get_measurements(
            sensor_uuid=sensor_uuid,
            begin_epoch=begin_ts,
            end_epoch=end_ts,
            timezone="UTC",
            sampling="P",
            value=0,
            limit=5000,
        )

        if not series:
            return None

        def ts_key(m: dict[str, str]) -> pd.Timestamp:
            t: str = m.get("timestamp") or m.get("ts") or m.get("date")  # type: ignore[assignment]
            try:
                return pd.to_datetime(t) if t else pd.Timestamp.min
            except Exception:
                return pd.Timestamp.min

        last = max(series, key=ts_key)

        return {
            "value": last.get("value"),
            "timestamp": last.get("timestamp") or last.get("ts") or last.get("date"),
            "raw": last,
        }
