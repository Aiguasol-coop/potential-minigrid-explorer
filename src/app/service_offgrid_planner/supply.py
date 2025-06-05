import datetime
import typing

import pydantic


class Sequences(pydantic.BaseModel):
    index: list[datetime.datetime]
    """Datetime index of the year to simulate."""

    demand: list[float]
    """Electrical demand as hourly timeseries over a year."""

    solar_potential: list[float]
    """Solar_potential from pvlib using era5 weather data as hourly timeseries over a year."""

    @pydantic.model_validator(mode="after")
    def check_lengths_match(self) -> typing.Self:
        n_index = len(self.index)
        n_demand = len(self.demand)
        n_solar = len(self.solar_potential)
        if not (n_index == n_demand == n_solar):
            raise ValueError(
                f"All sequences must have the same length: "
                f"index={n_index}, demand={n_demand}, solar_potential={n_solar}"
            )
        return self


class Settings(pydantic.BaseModel):
    is_selected: bool
    design: bool | None = None


class BatteryParameters(pydantic.BaseModel):
    nominal_capacity: float | None
    lifetime: int
    capex: float
    opex: float
    soc_min: float
    soc_max: float
    c_rate_in: float
    c_rate_out: float
    efficiency: float
    epc: float


class DieselGensetParameters(pydantic.BaseModel):
    nominal_capacity: float | None
    lifetime: int
    capex: float
    opex: float
    variable_cost: float
    fuel_cost: float
    fuel_lhv: float
    min_load: float
    max_load: float
    min_efficiency: float
    max_efficiency: float
    epc: float


class InverterParameters(pydantic.BaseModel):
    nominal_capacity: float | None
    lifetime: int
    capex: float
    opex: float
    efficiency: float
    epc: float


class PVParameters(pydantic.BaseModel):
    nominal_capacity: float | None
    lifetime: int
    capex: float
    opex: float
    epc: float


class RectifierParameters(pydantic.BaseModel):
    nominal_capacity: float | None
    lifetime: int
    capex: float
    opex: float
    efficiency: float
    epc: float


class ShortageParameters(pydantic.BaseModel):
    max_shortage_total: float
    max_shortage_timestep: float
    shortage_penalty_cost: float


class Battery(pydantic.BaseModel):
    settings: Settings
    parameters: BatteryParameters


class DieselGenset(pydantic.BaseModel):
    settings: Settings
    parameters: DieselGensetParameters


class Inverter(pydantic.BaseModel):
    settings: Settings
    parameters: InverterParameters


class PV(pydantic.BaseModel):
    settings: Settings
    parameters: PVParameters


class Rectifier(pydantic.BaseModel):
    settings: Settings
    parameters: RectifierParameters


class Shortage(pydantic.BaseModel):
    settings: Settings
    parameters: ShortageParameters


class EnergySystemDesign(pydantic.BaseModel):
    battery: Battery
    diesel_genset: DieselGenset
    inverter: Inverter
    pv: PV
    rectifier: Rectifier
    shortage: Shortage


class SupplyDescriptor(pydantic.BaseModel):
    sequences: Sequences
    energy_system_design: EnergySystemDesign


if __name__ == "__main__":
    import pathlib

    json_string = pathlib.Path("./tests/examples/supply_opt_json.json").read_text()
    supply = SupplyDescriptor.model_validate_json(json_string)
    print(supply.model_dump())
