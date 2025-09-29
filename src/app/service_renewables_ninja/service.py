import httpx


def get_pv_data(
    lat: float,
    lon: float,
) -> list[float]:
    """
    Fetch PV data from renewables.ninja. Returns hourly electricity potential in kW, for a complete
    year.

    Raises httpx.TimeoutException, httpx.HTTPStatusError or json.JSONDecodeError on error.
    """
    params = {
        "lat": lat,
        "lon": lon,
        # The only year available seems to be 2019:
        "date_from": "2019-01-01",
        "date_to": "2019-12-31",
        "dataset": "merra2",
        "capacity": 1,
        "system_loss": 0.1,
        "tracking": 0,
        "tilt": 35,
        "azim": 180,
        # TODO: if local_time is True, the time series returned is the same (first element has hour
        # 02:00).
        "local_time": False,  # The returned time series is in UTC
        "header": False,
        "format": "json",
    }

    BASE_URL = "https://www.renewables.ninja/api/data/pv"
    RN_API_TOKEN = "4e7ac9836e051491af9bc7ad2696aff16be22075"
    resp = httpx.get(BASE_URL, params=params, timeout=30.0, headers={"Authorization": RN_API_TOKEN})
    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 400:
            # print the body returned by the service for debugging
            try:
                err = exc.response.json()
            except Exception:
                err = exc.response.text
            print("renewables.ninja 400 error:", err)
        raise

    return [v["electricity"] for v in resp.json().values()]


if __name__ == "__main__":
    try:
        print("Call it!")
        data = get_pv_data(
            lat=-16.724031,
            lon=37.844604,
        )
        print(data)
    except Exception as exc:
        print("Error fetching wind data:", exc)
