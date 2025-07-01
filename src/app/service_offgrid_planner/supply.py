import datetime
import enum
import json
import typing

import pydantic


class Freq(str, enum.Enum):
    h = "h"


class Index(pydantic.BaseModel):
    start_date: datetime.datetime
    n_days: int = pydantic.Field(..., ge=1)
    freq: Freq


class Sequences(pydantic.BaseModel):
    index: Index

    demand: list[float]
    """Electrical demand as hourly timeseries over a year."""

    solar_potential: list[float]
    """Solar_potential from pvlib using era5 weather data as hourly timeseries over a year."""

    @pydantic.model_validator(mode="after")
    def check_lengths_match(self) -> typing.Self:
        match self.index.freq:
            case Freq.h:
                n_index = 24 * self.index.n_days

        n_demand = len(self.demand)
        n_solar = len(self.solar_potential)
        if not (n_index == n_demand == n_solar):
            raise ValueError(
                f"All sequences must have the same length: "
                f"index={n_index}, demand={n_demand}, solar_potential={n_solar}"
            )
        return self


class SettingsShortage(pydantic.BaseModel):
    is_selected: bool


class ParametersShortage(pydantic.BaseModel):
    max_shortage_total: float
    max_shortage_timestep: float
    shortage_penalty_cost: float


class Shortage(pydantic.BaseModel):
    settings: SettingsShortage
    parameters: ParametersShortage


class Settings(pydantic.BaseModel):
    is_selected: bool
    design: bool


class Parameters(pydantic.BaseModel):
    nominal_capacity: float | None = None
    soc_min: float | None = None
    soc_max: float | None = None
    c_rate_in: float | None = None
    c_rate_out: float | None = None
    efficiency: float | None = None
    epc: float | None = None
    variable_cost: float | None = None
    fuel_cost: float | None = None
    fuel_lhv: float | None = None
    min_load: float | None = None
    max_load: float | None = None
    min_efficiency: float | None = None
    max_efficiency: float | None = None
    capex: float | None = None
    opex: float | None = None
    lifetime: float | None = None


class Component(pydantic.BaseModel):
    settings: Settings
    parameters: Parameters


class EnergySystemDesign(pydantic.BaseModel):
    battery: Component
    diesel_genset: Component
    inverter: Component
    pv: Component
    rectifier: Component
    shortage: Shortage


class SupplyInput(pydantic.BaseModel):
    sequences: Sequences
    energy_system_design: EnergySystemDesign


class ScalarKey(str, enum.Enum):
    init_content = "init_content"
    invest = "invest"


class ResultKey(str, enum.Enum):
    battery_none = "battery__None"
    battery_electricity_dc = "battery__electricity_dc"
    diesel_genset_electricity_ac = "diesel_genset__electricity_ac"
    electricity_ac_demand = "electricity_ac__electricity_demand"
    electricity_ac_rectifier = "electricity_ac__rectifier"
    electricity_ac_surplus = "electricity_ac__surplus"
    electricity_dc_battery = "electricity_dc__battery"
    electricity_dc_inverter = "electricity_dc__inverter"
    fuel_diesel_genset = "fuel__diesel_genset"
    fuel_source_fuel = "fuel_source__fuel"
    inverter_electricity_ac = "inverter__electricity_ac"
    pv_electricity_dc = "pv__electricity_dc"
    rectifier_electricity_dc = "rectifier__electricity_dc"
    shortage_electricity_ac = "shortage__electricity_ac"


class ResultItem(pydantic.BaseModel):
    scalars: dict[ScalarKey, float]
    sequences: list[float]

    @pydantic.field_validator("scalars", mode="before")
    @classmethod
    def parse_scalars(cls, v: str | dict[ScalarKey, float]) -> dict[ScalarKey, float]:
        if isinstance(v, str):
            return json.loads(v)
        return v


class ServerInfo(str, enum.Enum):
    grid = "grid"
    supply = "supply"


class RequestStatus(str, enum.Enum):
    pending = "PENDING"
    done = "DONE"
    # TODO: add all the states


class SupplyOutput(pydantic.BaseModel):
    server_info: ServerInfo | None
    id: str
    status: RequestStatus
    results: dict[ResultKey, ResultItem] | None


if __name__ == "__main__":
    import pathlib
    import time

    import httpx

    input_json = pathlib.Path("./tests/examples/supply_input_example.json").read_text()
    supply_input = SupplyInput.model_validate_json(input_json)
    # print(supply.model_dump())

    response_send = httpx.post(
        url="https://optimizer-offgridplanner-app.apps2.rl-institut.de/sendjson/supply",
        json=supply_input.model_dump(mode="json"),
    )
    print(f"send response status code: {response_send.status_code}")

    if response_send.status_code != 200:
        exit(0)

    result_send = SupplyOutput.model_validate(response_send.json())

    time.sleep(20)
    response_check = httpx.get(
        url=f"https://optimizer-offgridplanner-app.apps2.rl-institut.de/check/{result_send.id}",
    )
    print(f"check response status code: {response_check.status_code}")

    if response_check.status_code != 200:
        exit(0)

    supply_output = SupplyOutput.model_validate(response_check.json())
    # Write the output to a JSON file
    output_path = pathlib.Path("./supply_output_from_service.json")
    output_path.write_text(supply_output.model_dump_json(indent=2))
    print(f"Supply output written to {output_path}")
