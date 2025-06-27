import collections.abc as abc
import enum
import typing

import httpx
import pydantic

import app.service_offgrid_planner.grid as grid
import app.service_offgrid_planner.supply as supply
import app.settings


class ServerInfo(str, enum.Enum):
    GRID = "grid"
    SUPPLY = "supply"


class RequestStatus(str, enum.Enum):
    PENDING = "PENDING"
    DONE = "DONE"
    ERROR = "ERROR"


ResultType = typing.TypeVar("ResultType")


class ErrorResultType(pydantic.BaseModel):
    ERROR: str
    INPUT_JSON: typing.Any


class OptimizerOutput(pydantic.BaseModel, typing.Generic[ResultType]):
    server_info: ServerInfo | None
    id: str  # TODO: what UUID version?
    status: RequestStatus
    results: ResultType | ErrorResultType | None


class ErrorServiceOffgridPlanner(str, enum.Enum):
    service_unavailable = "Service offgrid planner is currently unavailable"
    request_failed = "The request to service offgrid planner failed"


def _send_input_to_optimizer(
    input: grid.GridInput | supply.SupplyInput,
) -> (
    abc.Callable[
        [],
        OptimizerOutput[grid.GridResult]
        | OptimizerOutput[supply.SupplyResult]
        | ErrorServiceOffgridPlanner,
    ]
    | ErrorServiceOffgridPlanner
):
    settings = app.settings.get_settings()

    if isinstance(input, grid.GridInput):
        server_info = "grid"
    else:
        server_info = "supply"

    try:
        response_send = httpx.post(
            url=f"{settings.service_offgrid_planner_url}/sendjson/{server_info}",
            content=input.model_dump_json(),
        )
    except httpx.TimeoutException:
        return ErrorServiceOffgridPlanner.service_unavailable

    result_send = OptimizerOutput[grid.GridResult].model_validate(response_send.json())

    if response_send.status_code != 200:
        return ErrorServiceOffgridPlanner.request_failed

    def checker():
        try:
            response_check = httpx.get(
                url=f"{settings.service_offgrid_planner_url}/check/{result_send.id}",
            )
        except httpx.TimeoutException:
            return ErrorServiceOffgridPlanner.service_unavailable
        if response_check.status_code != 200:
            return ErrorServiceOffgridPlanner.request_failed
        if isinstance(input, grid.GridInput):
            output = OptimizerOutput[grid.GridResult].model_validate(response_check.json())
        else:
            output = OptimizerOutput[supply.SupplyResult].model_validate(response_check.json())
        if output.status == RequestStatus.ERROR:
            return ErrorServiceOffgridPlanner.request_failed

        return output

    return checker


def optimize_grid(
    input: grid.GridInput,
) -> (
    abc.Callable[[], OptimizerOutput[grid.GridResult] | ErrorServiceOffgridPlanner]
    | ErrorServiceOffgridPlanner
):
    """Returns a function to check the result (you can check repeatedly, until the optimization
    algorithm has finished)."""

    output = _send_input_to_optimizer(input)

    return output  # type: ignore


def optimize_supply(
    input: supply.SupplyInput,
) -> (
    abc.Callable[[], OptimizerOutput[supply.SupplyResult] | ErrorServiceOffgridPlanner]
    | ErrorServiceOffgridPlanner
):
    """Returns a function to check the result (you can check repeatedly, until the optimization
    algorithm has finished)."""

    output = _send_input_to_optimizer(input)

    return output  # type: ignore


if __name__ == "__main__":
    import pathlib
    import time

    ### Test grid optimizer

    input_json = pathlib.Path("./tests/examples/grid_input_example.json").read_text()
    grid_input = grid.GridInput.model_validate_json(input_json)

    checker_grid = optimize_grid(grid_input)
    print("Grid input sent for optimization (this can take >3s)")

    if isinstance(checker_grid, ErrorServiceOffgridPlanner):
        print("Sending grid input failed")
        exit(1)

    grid_output = checker_grid()
    while isinstance(grid_output, OptimizerOutput) and grid_output.status == RequestStatus.PENDING:
        time.sleep(1)
        grid_output = checker_grid()

    if isinstance(grid_output, ErrorServiceOffgridPlanner):
        print("Checking grid result failed")
        exit(1)

    output_path = pathlib.Path("./grid_output_from_service.json")
    output_path.write_text(grid_output.model_dump_json(indent=2))
    print(f"Grid output written to {output_path}")

    ### Test supply optimizer

    input_json = pathlib.Path("./tests/examples/supply_input_example.json").read_text()
    supply_input = supply.SupplyInput.model_validate_json(input_json)

    checker_supply = optimize_supply(supply_input)
    print("Supply input sent for optimization (this can take >10s)")

    if isinstance(checker_supply, ErrorServiceOffgridPlanner):
        print("Sending supply input failed")
        exit(1)

    supply_output = checker_supply()
    while (
        isinstance(supply_output, OptimizerOutput) and supply_output.status == RequestStatus.PENDING
    ):
        time.sleep(1)
        supply_output = checker_supply()

    if isinstance(supply_output, ErrorServiceOffgridPlanner):
        print("Checking supply result failed")
        exit(1)

    output_path = pathlib.Path("./supply_output_from_service.json")
    output_path.write_text(supply_output.model_dump_json(indent=2))
    print(f"Supply output written to {output_path}")
