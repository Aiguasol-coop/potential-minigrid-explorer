import uuid
import pydantic
import typing
import pandas as pd
import numpy as np
import sqlmodel

import app.service_offgrid_planner.supply as supply
import app.service_offgrid_planner.grid as grid


T = typing.TypeVar("T", supply.EnergySystemDesign, grid.GridDesign)


class Results(pydantic.BaseModel):
    n_consumers: int | None = None
    n_shs_consumers: int | None = None
    n_poles: int | None = None
    n_distribution_links: int | None = None
    n_connection_links: int | None = None
    length_distribution_cable: int | None = None
    average_length_distribution_cable: float | None = None
    length_connection_cable: int | None = None
    average_length_connection_cable: float | None = None
    cost_grid: int | None = None
    cost_shs: int | None = None
    lcoe: int | None = None
    res: float | None = None
    shortage_total: float | None = None
    surplus_rate: float | None = None
    cost_renewable_assets: float | None = None
    cost_non_renewable_assets: float | None = None
    cost_fuel: float | None = None
    pv_capacity: float | None = None
    battery_capacity: float | None = None
    inverter_capacity: float | None = None
    rectifier_capacity: float | None = None
    diesel_genset_capacity: float | None = None
    peak_demand: float | None = None
    surplus: float | None = None
    fuel_to_diesel_genset: float | None = None
    diesel_genset_to_rectifier: float | None = None
    diesel_genset_to_demand: float | None = None
    rectifier_to_dc_bus: float | None = None
    pv_to_dc_bus: float | None = None
    battery_to_dc_bus: float | None = None
    dc_bus_to_battery: float | None = None
    dc_bus_to_inverter: float | None = None
    dc_bus_to_surplus: float | None = None
    inverter_to_demand: float | None = None
    time_grid_design: float | None = None
    time_energy_system_design: float | None = None
    time: float | None = None
    co2_savings: float | None = None
    max_voltage_drop: float | None = None
    infeasible: int | None = None
    average_annual_demand_per_consumer: float | None = None
    total_annual_consumption: float | None = None
    upfront_invest_grid: float | None = None
    upfront_invest_diesel_gen: float | None = None
    upfront_invest_inverter: float | None = None
    upfront_invest_rectifier: float | None = None
    upfront_invest_battery: float | None = None
    upfront_invest_pv: float | None = None
    co2_emissions: float | None = None
    fuel_consumption: float | None = None
    base_load: float | None = None
    max_shortage: float | None = None
    epc_total: float | None = None
    epc_pv: float | None = None
    epc_diesel_genset: float | None = None
    epc_inverter: float | None = None
    epc_rectifier: float | None = None
    epc_battery: float | None = None


class ResultsSummary(pydantic.BaseModel):
    lcoe: float | None = None
    """Levelized cost of energy. Units: $/kWh."""

    capex: float | None = None
    """Capital expenditure. Units: $US."""

    res: float | None = sqlmodel.Field(ge=0.0, le=100.0, default=None)
    """Renewable energy share."""

    co2_savings: float | None = None
    """CO2 emission savings. Units: tonne/year."""

    consumption_total: float | None = None
    """Total consumption. Units: kWh/year."""


class Project:
    def __init__(self, id: pydantic.UUID4):
        self.id = id
        self.n_days = 365
        self.interest_rate = 5.0
        self.tax = 0.18
        self.lifetime = 20
        self.wacc = self.interest_rate / 100
        self.crf = (self.wacc * (1 + self.wacc) ** self.lifetime) / (
            (1 + self.wacc) ** self.lifetime - 1
        )

        self.grid_inputs: grid.GridInput | None = None
        self.supply_inputs: supply.SupplyInput | None = None
        self.grid_outputs: grid.GridResult | None = None
        self.supply_outputs: supply.SupplyResult | None = None

        self.results = Results()
        self.results_summary = ResultsSummary()

    def load_grid_inputs(self):
        if self.grid_inputs is None:
            raise ValueError("Grid inputs not set. Please define grid inputs first.")

        self.grid_design_dict = self.grid_inputs.grid_design
        self.grid_components = self.grid_design_dict.model_fields_set

        self.grid_design_dict = self.add_epc_to_dict(
            self.grid_design_dict, ["distribution_cable", "connection_cable", "pole"]
        )
        self.grid_design_dict.mg.epc = self.epc(
            self.grid_design_dict.mg.connection_cost, 0, self.lifetime
        )

    def load_supply_inputs(self):
        if self.supply_inputs is None:
            raise ValueError("Supply inputs not set. Please define supply inputs first.")

        self.energy_system_dict = self.supply_inputs.energy_system_design
        self.supply_components = self.energy_system_dict.model_fields_set

        self.demand = np.array(self.supply_inputs.sequences.demand)
        self.demand_full_year = np.array(self.demand) * 365 / self.n_days

        self.energy_system_dict = self.add_epc_to_dict(
            self.energy_system_dict,
            ["battery", "diesel_genset", "inverter", "rectifier", "pv"],
        )

    def annualize(self, value: float | None) -> float:
        return value / self.n_days * 365 if value is not None else 0

    def add_epc_to_dict(self, design: T, components: list[str]) -> T:
        """
        Compute and inject EPC (annualized per-unit cost) into each specified component
        of either an EnergySystemDesign or a GridDesign Pydantic model.
        """
        comps = set(components)

        # ----- Supply side: each component has .parameters.capex, .parameters.opex,
        # .parameters.lifetime
        if "supply_components" in self.__dict__ and comps.issubset(self.supply_components):
            for name in components:
                comp = getattr(design, name)
                p = comp.parameters
                if p.capex is None or p.opex is None or p.lifetime is None:
                    raise ValueError(f"Missing capex/opex/lifetime on supply component {name!r}")
                p.epc = self.epc(p.capex, p.opex, p.lifetime)

        # ----- Grid side: components have .capex, .lifetime, and top-level .epc to set
        elif "grid_components" in self.__dict__ and comps.issubset(self.grid_components):
            for name in components:
                comp = getattr(design, name)
                capex = getattr(comp, "capex", None)
                lifetime = getattr(comp, "lifetime", None)
                if capex is None or lifetime is None:
                    raise ValueError(f"Missing capex/lifetime on grid component {name!r}")
                # grid opex is always zero
                comp.epc = self.epc(capex, 0.0, lifetime)

        else:
            raise ValueError(
                "Components must be entirely in either supply_components or grid_components"
            )

        return design

    def epc(self, capex: float, opex: float, lifetime: float):
        epc = self.annualize(
            self.crf
            * self.capex_multi_investment(
                capex_0=capex,
                component_lifetime=lifetime,
            )
            + opex,
        )

        return epc

    def capex_multi_investment(self, capex_0: float, component_lifetime: float) -> float:
        """
        Calculates the equivalent CAPEX for components
        with lifetime less than the self.project lifetime.

        """
        # convert the string type into the float type for both inputs
        capex_0 = capex_0
        component_lifetime = component_lifetime
        if self.lifetime == component_lifetime:
            number_of_investments: int = 1
        else:
            number_of_investments: int = round(self.lifetime / component_lifetime + 0.5)  # type: ignore
        first_time_investment = capex_0 * (1 + self.tax)
        capex = first_time_investment
        for count_of_replacements in range(1, number_of_investments):
            if count_of_replacements * component_lifetime != self.lifetime:
                capex += first_time_investment / (
                    (1 + self.wacc) ** (count_of_replacements * component_lifetime)
                )
        # Subtraction of component value at end of life
        # with last replacement (= number_of_investments - 1)
        # This part calculates the salvage costs
        if number_of_investments * component_lifetime > self.lifetime:
            last_investment = first_time_investment / (
                (1 + self.wacc) ** ((number_of_investments - 1) * component_lifetime)
            )
            linear_depreciation_last_investment = last_investment / component_lifetime
            capex = capex - linear_depreciation_last_investment * (
                number_of_investments * component_lifetime - self.lifetime
            ) / ((1 + self.wacc) ** self.lifetime)
        return capex

    ### Grid functions:

    def _total_length(self, link_type: str) -> float:
        """
        Returns the sum of `length` over all links of the given type.
        """
        return float(self.links_df.length[self.links_df.link_type == link_type].sum())

    def grid_cost(self, n_poles: int, n_mg_consumers: int, n_links: int) -> float:
        """
        Computes the EPC‐based cost of the entire grid.
        """

        if n_poles == 0 or n_links == 0:
            return float("inf")

        # pull in both cable lengths via our new helper
        dist_len = self._total_length("distribution")
        conn_len = self._total_length("connection")

        cost = (
            n_poles * self.grid_design_dict.pole.epc
            + n_mg_consumers * self.grid_design_dict.mg.epc
            + conn_len * self.grid_design_dict.connection_cable.epc
            + dist_len * self.grid_design_dict.distribution_cable.epc
        )
        return round(cost, 2)

    def grid_results(self):
        if self.grid_outputs is None:
            raise ValueError("Grid outputs not set. Please define grid outputs first.")

        self.nodes_obj = self.grid_outputs.nodes
        self.links_obj: grid.Links = self.grid_outputs.links
        self.nodes_df = pd.DataFrame(dict(self.nodes_obj))
        self.links_df = pd.DataFrame(dict(self.links_obj))

        # 2) compute counts & lengths
        df = self.nodes_df
        n_consumers = int((df.node_type == "consumer").sum())
        n_shs_consumers = int((~df.is_connected).sum())
        n_poles = int(((df.node_type == "pole") | (df.node_type == "power-house")).sum())
        n_mg_consumers = n_consumers - n_shs_consumers

        dist_len = self._total_length("distribution")
        conn_len = self._total_length("connection")
        total_links = len(self.links_df)

        # 3) fill in results
        res = self.results
        res.n_consumers = n_consumers
        res.n_shs_consumers = n_shs_consumers
        res.n_poles = n_poles
        res.n_distribution_links = int((self.links_df.link_type == "distribution").sum())
        res.n_connection_links = int((self.links_df.link_type == "connection").sum())
        res.length_distribution_cable = int(dist_len)
        res.length_connection_cable = int(conn_len)

        # cost of grid & SHS
        res.cost_grid = (
            int(self.grid_cost(n_poles, n_mg_consumers, total_links)) if total_links > 0 else 0
        )
        res.cost_shs = 0

        # upfront investment
        res.upfront_invest_grid = (
            n_poles * self.grid_design_dict.pole.capex
            + dist_len * self.grid_design_dict.distribution_cable.capex
            + conn_len * self.grid_design_dict.connection_cable.capex
            + int(((df.consumer_type == "household") & df.is_connected).sum())
            * self.grid_design_dict.mg.connection_cost
        )

    # Supply functions:
    def _process_supply_optimization_results(self):
        results = self.supply_outputs

        self.sequences = {
            "pv": {"comp": "pv", "key": "pv__electricity_dc"},
            "genset": {
                "comp": "diesel_genset",
                "key": "diesel_genset__electricity_ac",
            },
            "battery_charge": {
                "comp": "battery",
                "key": "electricity_dc__battery",
            },
            "battery_discharge": {
                "comp": "battery",
                "key": "battery__electricity_dc",
            },
            "battery_content": {
                "comp": "battery",
                "key": "battery__None",
            },
            "inverter": {
                "comp": "inverter",
                "key": "inverter__electricity_ac",
            },
            "rectifier": {
                "comp": "rectifier",
                "key": "rectifier__electricity_dc",
            },
            "surplus": {
                "comp": "surplus",
                "key": "electricity_ac__surplus",
            },
            "shortage": {
                "comp": "shortage",
                "key": "shortage__electricity_ac",
            },
            "demand": {
                "comp": "demand",
                "key": "electricity_ac__electricity_demand",
            },
        }

        self.pv = self.energy_system_dict.pv
        self.diesel_genset = self.energy_system_dict.diesel_genset
        self.battery = self.energy_system_dict.battery
        self.inverter = self.energy_system_dict.inverter
        self.rectifier = self.energy_system_dict.rectifier
        self.shortage = self.energy_system_dict.shortage
        self.fuel_density_diesel = 0.846

        for seq, val in self.sequences.items():
            item: supply.ResultItem = getattr(results, val["key"])
            seq_data = item.sequences
            setattr(self, f"sequences_{seq}", np.array(seq_data))

        # Fuel consumption conversion
        item: supply.ResultItem = getattr(results, "fuel_source__fuel")
        seq_data = item.sequences
        self.sequences_fuel_consumption_kWh = np.array(seq_data)

        self.sequences_fuel_consumption = (
            self.sequences_fuel_consumption_kWh
            / self.diesel_genset.parameters.fuel_lhv
            / self.fuel_density_diesel
        )

        # SCALARS (STATIC)
        def get_capacity(component: supply.Component, result_key: str) -> float:
            if not component.settings.is_selected:
                return 0
            else:
                if component.settings.design:
                    return getattr(results, result_key).scalars["invest"]
                else:
                    return (
                        component.parameters.nominal_capacity
                        if component.parameters.nominal_capacity is not None
                        else 0
                    )

        self.capacity_diesel_genset = get_capacity(
            self.diesel_genset,
            "diesel_genset__electricity_ac",
        )
        self.capacity_pv = get_capacity(self.pv, "pv__electricity_dc")
        self.capacity_inverter = get_capacity(self.inverter, "electricity_dc__inverter")
        self.capacity_rectifier = get_capacity(self.rectifier, "electricity_ac__rectifier")
        self.capacity_battery = get_capacity(self.battery, "electricity_dc__battery")

        # Cost and energy calculations
        self.total_renewable = self.annualize(
            sum(
                getattr(self.energy_system_dict, comp).parameters.epc
                * getattr(self, f"capacity_{comp}")
                for comp in ["pv", "inverter", "battery"]
            )
        )

        self.total_non_renewable = (
            self.annualize(
                sum(
                    getattr(self.energy_system_dict, comp).parameters.epc
                    * getattr(self, f"capacity_{comp}")
                    for comp in ["diesel_genset", "rectifier"]
                )
            )
            + self.diesel_genset.parameters.variable_cost * self.sequences_genset.sum()
        )

        self.total_component = self.total_renewable + self.total_non_renewable
        self.total_fuel = (
            self.diesel_genset.parameters.fuel_cost * self.sequences_fuel_consumption.sum()
        )
        self.total_revenue = self.total_component + self.total_fuel
        self.total_demand = self.sequences_demand.sum()
        self.lcoe = 100 * self.total_revenue / self.total_demand

        # Key performance indicators
        self.res = (
            100 * self.sequences_pv.sum() / (self.sequences_genset.sum() + self.sequences_pv.sum())
        )
        self.surplus_rate = (
            100
            * self.sequences_surplus.sum()
            / (
                self.sequences_genset.sum()
                - self.sequences_rectifier.sum()
                + self.sequences_inverter.sum()
            )
        )
        self.genset_to_dc = 100 * self.sequences_rectifier.sum() / self.sequences_genset.sum()
        self.shortage = 100 * self.sequences_shortage.sum() / self.sequences_demand.sum()

    def supply_results(self):
        if self.grid_outputs is None:
            raise ValueError("Grid outputs not set. Please define grid outputs first.")

        nodes_df = self.nodes_df
        self.num_households = len(
            nodes_df[
                (nodes_df["consumer_type"] == "household") & (nodes_df["is_connected"] == True)  # noqa:E712
            ]
        )

        self._process_supply_optimization_results()
        self._emissions()
        self._results()

    def _emissions(self):
        # TODO check what the source is for these values and link here
        emissions_genset = {
            "small": {"max_capacity": 60, "emission_factor": 1.580},
            "medium": {"max_capacity": 300, "emission_factor": 0.883},
            "large": {"emission_factor": 0.699},
        }
        if self.capacity_diesel_genset < emissions_genset["small"]["max_capacity"]:
            co2_emission_factor = emissions_genset["small"]["emission_factor"]
        elif self.capacity_diesel_genset < emissions_genset["medium"]["max_capacity"]:
            co2_emission_factor = emissions_genset["medium"]["emission_factor"]
        else:
            co2_emission_factor = emissions_genset["large"]["emission_factor"]
        # store fuel co2 emissions (kg_CO2 per L of fuel)
        df = pd.DataFrame()
        df["non_renewable_electricity_production"] = (
            np.cumsum(self.demand) * co2_emission_factor / 1000
        )  # tCO2 per year
        df["hybrid_electricity_production"] = (
            np.cumsum(self.sequences_genset) * co2_emission_factor / 1000
        )  # tCO2 per year
        df.index = pd.date_range("2022-01-01", periods=df.shape[0], freq="h")
        df = df.resample("D").max().reset_index(drop=True)

        self.co2_savings = (
            df["non_renewable_electricity_production"] - df["hybrid_electricity_production"]
        ).max()
        self.co2_emission_factor = co2_emission_factor

    def _results(self):
        # Annualized cost calculations
        def to_kwh(value: float | None) -> float:
            """Adapt the order of magnitude (normally from W or Wh oemof results to kWh)"""
            return value / 1000 if value is not None else 0

        results = self.results

        # Handle missing cost_grid case
        if pd.isna(results.cost_grid):
            zero_fields = [
                "n_consumers",
                "n_shs_consumers",
                "n_poles",
                "length_distribution_cable",
                "length_connection_cable",
                "cost_grid",
                "cost_shs",
                "time_grid_design",
                "n_distribution_links",
                "n_connection_links",
                "upfront_invest_grid",
            ]
            for field in zero_fields:
                setattr(results, field, 0)

        results.cost_renewable_assets = self.annualize(self.total_renewable)
        results.cost_non_renewable_assets = self.annualize(self.total_non_renewable)
        results.cost_fuel = self.annualize(self.total_fuel)
        results.cost_grid = self.annualize(results.cost_grid)

        # Financial calculations
        results.epc_total = self.annualize(self.total_revenue + results.cost_grid)
        results.lcoe = 100 * (self.total_revenue + results.cost_grid) / self.total_demand

        # System attributes
        results.res = self.res
        results.shortage_total = self.shortage
        results.surplus_rate = self.surplus_rate
        results.peak_demand = self.demand.max()
        results.surplus = self.sequences_surplus.max()
        # TODO no longer needed since sim server should return error
        # results.infeasible = self.infeasible

        # Component capacities
        capacity_fields = {
            "pv_capacity": self.capacity_pv,
            "battery_capacity": self.capacity_battery,
            "inverter_capacity": self.capacity_inverter,
            "rectifier_capacity": self.capacity_rectifier,
            "diesel_genset_capacity": self.capacity_diesel_genset,
        }
        for key, value in capacity_fields.items():
            setattr(results, key, value)

        # Sankey diagram energy flows (all in MWh)
        results.fuel_to_diesel_genset = to_kwh(
            self.sequences_fuel_consumption.sum() * 0.846 * self.diesel_genset.parameters.fuel_lhv
        )

        results.diesel_genset_to_rectifier = to_kwh(
            self.sequences_rectifier.sum() / self.rectifier.parameters.efficiency
        )

        results.diesel_genset_to_demand = (
            to_kwh(self.sequences_genset.sum()) - results.diesel_genset_to_rectifier
        )

        results.rectifier_to_dc_bus = to_kwh(self.sequences_rectifier.sum())
        results.pv_to_dc_bus = to_kwh(self.sequences_pv.sum())
        results.battery_to_dc_bus = to_kwh(self.sequences_battery_discharge.sum())
        results.dc_bus_to_battery = to_kwh(self.sequences_battery_charge.sum())

        inverter_efficiency = self.inverter.parameters.efficiency or 1
        results.dc_bus_to_inverter = to_kwh(self.sequences_inverter.sum() / inverter_efficiency)

        results.dc_bus_to_surplus = to_kwh(self.sequences_surplus.sum())
        results.inverter_to_demand = to_kwh(self.sequences_inverter.sum())

        # TODO no longer needed
        # results.time_energy_system_design = self.execution_time
        results.co2_savings = self.annualize(self.co2_savings)

        # Demand and shortage statistics
        results.total_annual_consumption = self.demand_full_year.sum() * (100 - self.shortage) / 100
        results.average_annual_demand_per_consumer = (
            self.demand_full_year.mean() * (100 - self.shortage) / 100 / self.num_households * 1000
        )
        results.base_load = np.quantile(self.demand_full_year, 0.1)
        results.max_shortage = (self.sequences_shortage / self.demand).max() * 100

        # Upfront investment calculations
        investment_fields = {
            "upfront_invest_diesel_gen": "diesel_genset",
            "upfront_invest_pv": "pv",
            "upfront_invest_inverter": "inverter",
            "upfront_invest_rectifier": "rectifier",
            "upfront_invest_battery": "battery",
        }
        for key, component in investment_fields.items():
            setattr(
                results,
                key,
                getattr(results, component + "_capacity")
                * getattr(self.energy_system_dict, component).parameters.capex,
            )

        # Environmental and fuel consumption calculations
        results.co2_emissions = self.annualize(
            self.sequences_genset.sum() * self.co2_emission_factor / 1000
        )
        results.fuel_consumption = self.annualize(self.sequences_fuel_consumption.sum())

        # EPC cost calculations
        epc_fields = {
            "epc_pv": "pv",
            "epc_diesel_genset": "diesel_genset",
            "epc_inverter": "inverter",
            "epc_rectifier": "rectifier",
            "epc_battery": "battery",
        }
        for key, component in epc_fields.items():
            setattr(
                results,
                key,
                getattr(self.energy_system_dict, component).parameters.epc
                * getattr(self, f"capacity_{component}"),
            )

        results.epc_diesel_genset += self.annualize(
            self.diesel_genset.parameters.variable_cost * self.sequences_genset.sum(axis=0)
        )

    def get_results_summary(self) -> ResultsSummary:
        """
        Returns a summary of the results, including LCOE, CAPEX, RES, CO2 savings,
        and total consumption.
        """
        res = self.results_summary

        res.lcoe = float(self.results.lcoe)
        res.capex = float(
            self.results.cost_grid
            + self.results.cost_renewable_assets
            + self.results.cost_non_renewable_assets
        )
        res.res = float(self.results.res)
        res.co2_savings = float(self.results.co2_savings)
        res.consumption_total = float(self.results.total_annual_consumption)

        return res


if __name__ == "__main__":
    import pathlib

    # Create a simulation class:
    simulation = Project(id=uuid.uuid4())

    # Load and add grid and supply inputs:
    input_json = pathlib.Path(
        "/workspaces/potential-minigrid-explorer/src/tests/examples/grid_input_example.json"
    ).read_text()
    grid_input = grid.GridInput.model_validate_json(input_json)
    simulation.grid_inputs = grid_input
    simulation.load_grid_inputs()

    input_json = pathlib.Path(
        "/workspaces/potential-minigrid-explorer/src/tests/examples/supply_input_example.json"
    ).read_text()
    supply_input = supply.SupplyInput.model_validate_json(input_json)
    simulation.supply_inputs = supply_input
    simulation.load_supply_inputs()

    # Load and add grid and supply outputs:
    grid_output_json = pathlib.Path(
        "/workspaces/potential-minigrid-explorer/src/tests/examples/grid_output_example.json"
    ).read_text()
    grid_output = grid.GridResult.model_validate_json(grid_output_json)
    simulation.grid_outputs = grid_output

    supply_output_json = pathlib.Path(
        "/workspaces/potential-minigrid-explorer/src/tests/examples/supply_output_example.json"
    ).read_text()
    supply_output = supply.SupplyResult.model_validate_json(supply_output_json)
    simulation.supply_outputs = supply_output

    # Compute the results:
    simulation.grid_results()
    simulation.supply_results()

    # Get results summary:
    simulation.get_results_summary()

    print(simulation.get_results_summary())
