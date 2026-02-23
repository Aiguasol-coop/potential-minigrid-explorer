from __future__ import annotations
import pandas as pd
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from typing import Any
import datetime

from app.monitoring.sds_client import SDSClient
from app.monitoring.domain import DASHBOARD_KPIS
from app.settings import Settings
from app.monitoring.domain import AlarmType


def normalize_ts(x: str) -> datetime.datetime | None:
    """Normalize timestamps to ISO string if possible."""
    if x in (None, ""):
        return None
    try:
        ts = pd.to_datetime(x, errors="coerce")
        if pd.isna(ts):
            return None
        # keep as ISO-like string
        return ts
    except Exception:
        return None


def is_stale(last_update: str | None, tz: str, max_age_minutes: int = 90) -> bool:
    """
    Returns True if last_update is missing or older than max_age_minutes in the given timezone.
    """
    if last_update is None:
        return True

    ts = pd.to_datetime(last_update, errors="coerce")
    if pd.isna(ts):
        return True

    # If no timezone info, assume it's already in component tz
    if ts.tzinfo is None:
        ts = ts.tz_localize(ZoneInfo(tz))
    else:
        ts = ts.tz_convert(ZoneInfo(tz))

    now = pd.Timestamp.now(tz=ZoneInfo(tz))
    age_seconds = (now - ts).total_seconds()

    # If timestamp is in the future (clock mismatch), consider it not stale
    if age_seconds < 0:
        return False

    return age_seconds > max_age_minutes * 60


def epoch_range_today(tz_name: str) -> tuple[int, int]:
    """
    Returns (begin_epoch, end_epoch) for today 00:00 to now in the given timezone.
    """
    tz = ZoneInfo(tz_name)
    now = pd.Timestamp.now(tz=tz)
    start = now.normalize()  # 00:00 local time
    return int(start.timestamp()), int(now.timestamp())


def sensor_uuid_by_name(sensors: list[dict[str, Any]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for s in sensors:
        name = (s.get("name") or s.get("alias") or "").strip()
        uuid = s.get("uuid") or s.get("sensoruuid") or s.get("id")
        if name and uuid:
            out[name] = uuid
    return out


def group_incidents_by_component(incidents: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for inc in incidents:
        cu = (
            inc.get("componentuuid")
            or inc.get("component_uuid")
            or inc.get("component")
            or inc.get("uuid_component")
        )
        if not cu:
            continue
        counts[cu] = counts.get(cu, 0) + 1
    return counts


def daily_energy_from_measurements(
    measurements: list[dict[str, Any]],
) -> tuple[float | None, str | None]:
    """
    Convert cumulative energy meter readings into 'today energy' (delta).
    Returns: (daily_kwh, last_update_str)
    """
    if not measurements:
        return None, None

    # Sort by timestamp just in case
    ms = sorted(measurements, key=lambda x: x.get("timestamp") or "")
    first = ms[0].get("value")
    last = ms[-1].get("value")
    last_ts = ms[-1].get("timestamp")

    if first is None or last is None:
        return None, last_ts

    delta = last - first

    # Some sensors return Wh counters (big numbers), some might return kWh.
    # Heuristic: if delta is very large, assume Wh and convert to kWh.
    # (You can adjust this threshold later.)
    if delta > 5000:  # 5000 kWh/day would be huge → likely Wh
        delta_kwh = delta / 1000.0
    else:
        delta_kwh = delta

    # Avoid negative daily due to resets/rollover
    if delta_kwh < 0:
        return None, last_ts

    return round(delta_kwh, 3), last_ts


def fetch_one_daily_kpi(
    client: SDSClient,
    sensor_uuid: str,
    tz: str,
) -> tuple[float | None, str | None]:
    begin_ts, end_ts = epoch_range_today(tz)
    measurements = client.get_measurements(sensor_uuid, begin_ts, end_ts)
    return daily_energy_from_measurements(measurements)


def pick(d: dict[str, Any], *keys: str, default: str = "") -> str:
    """Return the first existing non-empty key in dict."""
    for k in keys:
        if k in d and d[k] not in (None, "", [], {}):
            return d[k]
    return default


def build_alarms(
    client: SDSClient,
) -> list[dict[str, Any]]:
    """
    Build one row per incident/alarm (table-ready).
    incident_status is 'new' or 'open' depending on which list you're processing.
    """

    components = client.list_components()
    component_uuid_to_name: dict[Any, Any] = {}
    for c in components:
        u = c.get("uuid") or c.get("componentuuid") or c.get("id")
        n = c.get("name") or c.get("alias") or u
        if u:
            component_uuid_to_name[u] = n

    rows: list[dict[str, Any]] = []
    for alarm_type in AlarmType.__members__.values():
        try:
            incidents = client.list_incidents(status=alarm_type.value)
        except Exception as e:
            print(f"Warning: could not fetch {alarm_type.value.upper()} incidents:", e)
            continue

        for inc in incidents:
            comp_uuid = pick(
                inc, "componentuuid", "component_uuid", "component", "componentId", "component_id"
            )

            mini_grid = component_uuid_to_name.get(
                comp_uuid, pick(inc, "componentname", "component_name", default="(unknown)")
            )

            row = {
                "name": mini_grid,
                "component_uuid": comp_uuid,
                "status": alarm_type.value,
                "title": pick(inc, "name", "title", "alarm", "type", default=""),
                "description": pick(inc, "description", "message", "details", default=""),
                "device": pick(
                    inc, "device", "source", "origin", "sensor", "sensorname", default=""
                ),
                "created_at": normalize_ts(
                    pick(inc, "created_at", "createdAt", "created", "start", "begin", "timestamp")
                ),
                "updated_at": normalize_ts(
                    pick(inc, "updated_at", "updatedAt", "updated", "end", "last_update")
                ),
                "severity": pick(inc, "severity", "level", "priority", default=""),
                "incident_id": pick(inc, "uuid", "id", "incidentuuid", "incident_uuid", default=""),
                "raw": inc,  # keep raw payload for now (super useful for refining columns)
            }
            rows.append(row)

    # Most recent first
    def sort_key(r: dict[str, Any]) -> str:
        return (r.get("updated_at") or "", r.get("created_at") or "")  # type: ignore

    rows.sort(key=sort_key, reverse=True)

    return rows


def build_table(client: SDSClient, settings: Settings) -> pd.DataFrame:
    try:
        inc_new_list = client.list_incidents(status="new")
    except Exception as e:
        print("Warning: could not fetch NEW incidents:", e)
        inc_new_list = []

    try:
        inc_open_list = client.list_incidents(status="open")
    except Exception as e:
        print("Warning: could not fetch OPEN incidents:", e)
        inc_open_list = []

    inc_new = group_incidents_by_component(inc_new_list)
    inc_open = group_incidents_by_component(inc_open_list)

    components = client.list_components()
    sensor_cache_lock = Lock()
    sensor_workers = max(1, min(len(DASHBOARD_KPIS), settings.monitoring_workers))

    def build_component_row(comp: dict[str, Any]) -> dict[str, Any]:
        comp_uuid: str = comp.get("uuid")  # type: ignore[assignment]
        name = comp.get("name") or comp_uuid
        tz = comp.get("timezone") or "Africa/Maputo"

        with sensor_cache_lock:
            if comp_uuid not in client.sensor_cache:
                sensors = client.list_sensors(comp_uuid)
                client.sensor_cache[comp_uuid] = sensor_uuid_by_name(sensors)
            name_to_uuid: dict[str, str] = dict(client.sensor_cache[comp_uuid])

        row: dict[str, object] = {
            "name": name,
            "timezone": tz,
            "new_alarms": inc_new.get(comp_uuid, 0),
            "open_alarms": inc_open.get(comp_uuid, 0),
            "component_uuid": comp_uuid,
            "monitoring_url": f"{settings.monitoring_url_template}{comp_uuid}",
        }
        row["centroid"] = {
            "type": "Point",
            "coordinates": [comp.get("longitude"), comp.get("latitude")],
        }
        row["timezone"] = tz

        # Compute daily values in parallel per component (sensor-level)
        futures = {}
        with ThreadPoolExecutor(max_workers=sensor_workers) as sensor_ex:
            for sensor_name, col in DASHBOARD_KPIS.items():
                suuid = name_to_uuid.get(sensor_name)
                if not suuid:
                    row[col] = None
                    continue
                futures[sensor_ex.submit(fetch_one_daily_kpi, client, suuid, tz)] = col

            last_updates: list[str] = []
            for f in as_completed(futures):  # type: ignore
                col = futures[f]  # type: ignore
                try:
                    val, last_update_str = f.result()  # type: ignore
                except Exception as e:
                    print(f"  - Warning: {name} {col} failed:", e)
                    val, last_update_str = None, None

                row[col] = val
                if last_update_str:
                    last_updates.append(last_update_str)  # type: ignore

        # last_update = latest of KPI updates (string compare works for same format)
        row["last_update"] = max(last_updates) if last_updates else None
        row["stale"] = is_stale(
            row["last_update"], tz=tz, max_age_minutes=settings.stale_max_age_minutes
        )

        # Final status (priority: stale > incidents > ok)
        if row["stale"]:
            row["status"] = "RED"
        elif (row.get("incidents_new", 0) > 0) or (row.get("incidents_open", 0) > 0):  # type: ignore
            row["status"] = "ORANGE"
        else:
            row["status"] = "GREEN"

        return row  # type: ignore[return-value]

    rows: list[dict[str, Any]] = []
    # Parallelize both components and sensors (both IO-bound)
    with ThreadPoolExecutor(max_workers=settings.monitoring_workers) as comp_ex:
        futures = {
            comp_ex.submit(build_component_row, comp): idx for idx, comp in enumerate(components)
        }
        ordered_rows: list[dict[str, Any] | None] = [None] * len(components)

        for future in as_completed(futures):
            idx = futures[future]
            try:
                ordered_rows[idx] = future.result()
            except Exception as e:
                print(f"Warning: component processing failed at index {idx}:", e)

        rows = [row for row in ordered_rows if row is not None]

    df = pd.DataFrame(rows)
    df.replace({float("nan"): None}, inplace=True)  # Convert NaN to None for JSON serialization

    # Order columns like dashboard
    ordered = [
        "mini_grid",
        "status",
        "last_update",
        "consumption_kwh_day",
        "generation_kwh_day",
        "charged_kwh_day",
        "discharged_kwh_day",
        "self_consumption_kwh_day",
        "incidents_new",
        "incidents_open",
        "timezone",
        "component_uuid",
    ]
    cols = [c for c in ordered if c in df.columns] + [c for c in df.columns if c not in ordered]
    return df[cols]
