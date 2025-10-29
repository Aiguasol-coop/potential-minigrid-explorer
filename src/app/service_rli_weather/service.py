import numpy as np
import pandas as pd
import pvlib
from feedinlib import era5
import requests
import app.settings
import xarray as xr


def request_weather_data(
    latitude: float, longitude: float, *, timeinfo=False
) -> pd.DataFrame | tuple[pd.DataFrame, dict]:
    session = requests.Session()
    settings = app.settings.get_settings()

    # TODO one shouldn't need a csrftoken for server to server
    # fetch CSRF token
    csrf_response = session.get(settings.weather_data_api_host + "get_csrf_token/")
    csrftoken = csrf_response.json()["csrfToken"]

    payload = {"latitude": latitude, "longitude": longitude}

    # headers = {"content-type": "application/json"}
    headers = {
        "X-CSRFToken": csrftoken,
        "Referer": settings.weather_data_api_host,
    }

    post_response = session.post(settings.weather_data_api_host, data=payload, headers=headers)
    # TODO here would be best to return a token but this requires
    # celery on the weather_data API side
    # If we get a high request amount we might need to do so anyway
    if post_response.ok:
        response_data = post_response.json()
        df = pd.DataFrame(response_data["variables"])
        print("The weather data API fetch worked successfully")

        if timeinfo is True:
            timeindex = response_data["time"]
    else:
        df = pd.DataFrame()
        print("The weather data API fetch did not work")

    if timeinfo is False:
        return df
    else:
        return df, timeindex


def build_xarray_for_pvlib(lat: float, lon: float, dt_index: pd.DatetimeIndex) -> xr.Dataset:
    era5_units = {
        "d2m": {"units": "K", "long_name": "2 metre dewpoint temperature"},
        "e": {"units": "m", "long_name": "Evaporation (water equivalent)"},
        "fdir": {
            "units": "J/m²",
            "long_name": "Total sky direct solar radiation at surface",
        },
        "fsr": {"units": "1", "long_name": "Fraction of solar radiation"},
        "sp": {"units": "Pa", "long_name": "Surface pressure"},
        "ssrd": {"units": "J/m²", "long_name": "Surface solar radiation downwards"},
        "t2m": {"units": "K", "long_name": "2 metre temperature"},
        "tp": {"units": "m", "long_name": "Total precipitation"},
        "u10": {"units": "m/s", "long_name": "10 metre U wind component"},
        "u100": {"units": "m/s", "long_name": "100 metre U wind component"},
        "v10": {"units": "m/s", "long_name": "10 metre V wind component"},
        "v100": {"units": "m/s", "long_name": "100 metre V wind component"},
    }

    df = request_weather_data(lat, lon)
    df.index = dt_index
    df.index.name = "time"
    ds = df.to_xarray()

    # Attach scalar coords for the site
    ds = ds.assign_coords(latitude=float(lat), longitude=float(lon))

    # Add ERA5-style attributes expected by pvlib
    for var, attrs in era5_units.items():
        if var in ds:
            ds[var] = ds[var].assign_attrs(attrs)

    return ds


def prepare_weather_data(data_xr: xr.Dataset) -> pd.DataFrame:
    df = era5.format_pvlib(data_xr)
    df = df.reset_index()
    df = df.rename(columns={"time": "dt", "latitude": "lat", "longitude": "lon"})
    df = df.set_index(["dt"])
    df["dni"] = np.nan
    lat = float(data_xr.latitude)
    lon = float(data_xr.longitude)
    solar_position = pvlib.solarposition.get_solarposition(
        time=df.index,
        latitude=lat,
        longitude=lon,
    )
    df["dni"] = pvlib.irradiance.dni(
        ghi=df["ghi"],
        dhi=df["dhi"],
        zenith=solar_position["apparent_zenith"],
    ).fillna(0)
    df = df.reset_index()
    df["dt"] = df["dt"] - pd.Timedelta("30min")
    df["dt"] = df["dt"].dt.tz_convert("UTC").dt.tz_localize(None)
    df.iloc[:, 3:] = (df.iloc[:, 3:] + 0.0000001).round(1)
    df.loc[:, "lon"] = df.loc[:, "lon"].round(3)
    df.loc[:, "lat"] = df.loc[:, "lat"].round(7)
    df = df.set_index("dt")
    return df


def _get_dc_feed_in(lat: float, lon: float, weather_df: pd.DataFrame) -> pd.Series:
    module = pvlib.pvsystem.retrieve_sam("SandiaMod")["SolarWorld_Sunmodule_250_Poly__2013_"]
    inverter = pvlib.pvsystem.retrieve_sam("cecinverter")["ABB__MICRO_0_25_I_OUTD_US_208__208V_"]
    temperature_model_parameters = pvlib.temperature.TEMPERATURE_MODEL_PARAMETERS["sapm"][
        "open_rack_glass_glass"
    ]
    system = pvlib.pvsystem.PVSystem(
        surface_tilt=30,
        surface_azimuth=180,
        module_parameters=module,
        inverter_parameters=inverter,
        temperature_model_parameters=temperature_model_parameters,
    )
    location = pvlib.location.Location(latitude=lat, longitude=lon)
    mc = pvlib.modelchain.ModelChain(system, location)
    mc.run_model(weather=weather_df)
    dc_power = mc.results.dc["p_mp"].clip(0).fillna(0) / 1000
    return dc_power


def get_pv_data(lat: float, lon: float, dt_index: pd.DatetimeIndex) -> list[float]:
    cds_data = build_xarray_for_pvlib(lat, lon, dt_index)
    weather_df = prepare_weather_data(cds_data)
    solar_potential = _get_dc_feed_in(lat, lon, weather_df)

    return solar_potential.tolist()


if __name__ == "__main__":
    try:
        print("Call it!")
        data = get_pv_data(
            lat=-16.724031,
            lon=37.844604,
            dt_index=pd.date_range(
                start="2022-01-01 00:00:00", end="2022-12-31 23:00:00", freq="h"
            ),
        )
        print(data)
    except Exception as exc:
        print("Error fetching rli pv data:", exc)
