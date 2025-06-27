import enum
import typing

import pydantic

import app.service_offgrid_planner.grid as grid
import app.service_offgrid_planner.supply as supply


class ServerInfo(str, enum.Enum):
    GRID = "grid"
    SUPPLY = "supply"


class RequestStatus(str, enum.Enum):
    PENDING = "PENDING"
    DONE = "DONE"
    ERROR = "ERROR"


ResultType = typing.TypeVar("ResultType")


class OptimizerOutput(pydantic.BaseModel, typing.Generic[ResultType]):
    server_info: ServerInfo | None
    id: str  # TODO: what UUID version?
    status: RequestStatus
    results: ResultType | None


if __name__ == "__main__":
    import pathlib
    import time

    import httpx

    ### Test grid optimizer

    input_json = pathlib.Path("./tests/examples/grid_input_example.json").read_text()
    grid_input = grid.GridInput.model_validate_json(input_json)
    # print(supply.model_dump())

    response_send = httpx.post(
        url="https://optimizer-offgridplanner-app.apps2.rl-institut.de/sendjson/grid",
        content=grid_input.model_dump_json(),
    )
    print(f"send response status code: {response_send.status_code}")
    print(f"send response content: {response_send.json()}")

    result_send = OptimizerOutput[grid.GridResult].model_validate(response_send.json())

    time.sleep(5)
    response_check = httpx.get(
        url=f"https://optimizer-offgridplanner-app.apps2.rl-institut.de/check/{result_send.id}",
    )
    print(f"check response status code: {response_check.status_code}")

    if response_check.status_code != 200:
        exit(0)

    grid_output = OptimizerOutput[grid.GridResult].model_validate(response_check.json())
    # Write the output to a JSON file
    output_path = pathlib.Path("./grid_output_from_service.json")
    output_path.write_text(grid_output.model_dump_json(indent=2))
    print(f"Supply output written to {output_path}")

    ### Test supply optimizer

    input_json = pathlib.Path("./tests/examples/supply_input_example.json").read_text()
    supply_input = supply.SupplyInput.model_validate_json(input_json)
    # print(supply.model_dump())

    response_send = httpx.post(
        url="https://optimizer-offgridplanner-app.apps2.rl-institut.de/sendjson/supply",
        content=supply_input.model_dump_json(),
    )
    print(f"send response status code: {response_send.status_code}")
    print(f"send response content: {response_send.json()}")

    if response_send.status_code != 200:
        exit(0)

    result_send = OptimizerOutput[supply.SupplyResult].model_validate(response_send.json())

    time.sleep(20)
    response_check = httpx.get(
        url=f"https://optimizer-offgridplanner-app.apps2.rl-institut.de/check/{result_send.id}",
    )
    print(f"check response status code: {response_check.status_code}")

    if response_check.status_code != 200:
        exit(0)

    supply_output = OptimizerOutput[supply.SupplyResult].model_validate(response_check.json())
    # Write the output to a JSON file
    output_path = pathlib.Path("./supply_output_from_service.json")
    output_path.write_text(supply_output.model_dump_json(indent=2))
    print(f"Supply output written to {output_path}")
