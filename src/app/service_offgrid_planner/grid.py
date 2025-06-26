import enum
import typing

import pydantic


class HowAdded(str, enum.Enum):
    automatic = "automatic"
    manual = "manual"
    k_means = "k-means"
    long_distance = "long-distance"


class NodeType(str, enum.Enum):
    consumer = "consumer"
    pole = "pole"
    power_house = "power-house"


class ConsumerType(str, enum.Enum):
    household = "household"
    na = "n.a."


class CustomSpecLiteral(str, enum.Enum):
    none = "none"
    break_pole = "break-pole"


CustomSpecification = CustomSpecLiteral | str


class ConsumerDetail(str, enum.Enum):
    default = "default"
    na = "n.a."


ShsOptionsInt = typing.Annotated[int, pydantic.Field(ge=0, le=2)]


class NodeAttributes(pydantic.BaseModel):
    latitude: list[float]
    longitude: list[float]
    how_added: list[HowAdded]
    node_type: list[NodeType]
    consumer_type: list[ConsumerType]
    custom_specification: list[CustomSpecification | None]
    shs_options: list[ShsOptionsInt | None]  # TODO: it was list[ShsOptionsInt]
    consumer_detail: list[ConsumerDetail]
    is_connected: list[bool]
    # TODO: it was list[float] | None = None
    distance_to_load_center: list[float | None] | None = None
    distribution_cost: list[float | None] | None = None  # TODO: it was list[float] | None = None
    parent: list[str] | None = None

    @pydantic.model_validator(mode="after")
    def check_lengths_match(self) -> typing.Self:
        # List of all fields that should have the same length
        list_fields = [
            "latitude",
            "longitude",
            "how_added",
            "node_type",
            "consumer_type",
            "custom_specification",
            "shs_options",
            "consumer_detail",
            "is_connected",
        ]
        lengths = {field: len(getattr(self, field)) for field in list_fields}
        unique_lengths = set(lengths.values())
        if len(unique_lengths) > 1:
            raise ValueError(
                "All list fields must have the same length: "
                + ", ".join(f"{k}={v}" for k, v in lengths.items())
            )
        # Optionally check optional fields if they are not None
        optional_fields = [
            "distance_to_load_center",
            "distribution_cost",
            "parent",
        ]
        n = next(iter(unique_lengths))
        for field in optional_fields:
            value = getattr(self, field)
            if value is not None and len(value) != n:
                raise ValueError(f"Optional field '{field}' must have length {n}, got {len(value)}")
        return self


class DistributionCable(pydantic.BaseModel):
    lifetime: int
    capex: float
    max_length: float
    epc: float


class ConnectionCable(pydantic.BaseModel):
    lifetime: int
    capex: float
    max_length: float
    epc: float


class Pole(pydantic.BaseModel):
    lifetime: int
    capex: float
    max_n_connections: int
    epc: float


class Mg(pydantic.BaseModel):
    connection_cost: float
    epc: float


class Shs(pydantic.BaseModel):
    include: bool
    max_grid_cost: float


class GridDesign(pydantic.BaseModel):
    distribution_cable: DistributionCable
    connection_cable: ConnectionCable
    pole: Pole
    mg: Mg
    shs: Shs | None = None


class GridInput(pydantic.BaseModel):
    nodes: NodeAttributes
    grid_design: GridDesign
    yearly_demand: float


class Links(pydantic.BaseModel):
    lat_from: list[str]
    lon_from: list[str]
    lat_to: list[str]
    lon_to: list[str]
    link_type: list[str]
    length: list[float]


class SupplyResults(pydantic.BaseModel):
    nodes: NodeAttributes
    links: Links


class ServerInfo(str, enum.Enum):
    grid = "grid"
    supply = "supply"


class RequestStatus(str, enum.Enum):
    pending = "PENDING"
    done = "DONE"
    # TODO: add all the states


class GridOutput(pydantic.BaseModel):
    server_info: ServerInfo | None
    id: str  # TODO: what UUID version?
    status: RequestStatus
    results: SupplyResults


if __name__ == "__main__":
    import pathlib
    import time

    import httpx

    input_json = pathlib.Path("./tests/examples/grid_input_example.json").read_text()
    grid_input = GridInput.model_validate_json(input_json)
    # print(supply.model_dump())

    response_send = httpx.post(
        url="https://optimizer-offgridplanner-app.apps2.rl-institut.de/sendjson/grid",
        json=grid_input.model_dump(mode="json"),
    )
    print(f"send response status code: {response_send.status_code}")

    result_send = GridOutput.model_validate(response_send.json())

    time.sleep(5)
    response_check = httpx.get(
        url=f"https://optimizer-offgridplanner-app.apps2.rl-institut.de/check/{result_send.id}",
    )
    print(f"check response status code: {response_check.status_code}")

    if response_check.status_code != 200:
        exit(0)

    grid_output = GridOutput.model_validate(response_check.json())
    # Write the output to a JSON file
    output_path = pathlib.Path("./grid_output_from_service.json")
    output_path.write_text(grid_output.model_dump_json(indent=2))
    print(f"Supply output written to {output_path}")

    # # Example of how to update some deeply nested field in the example (the capex for poles):
    # new_grid_design_pole = grid.grid_design.pole.model_copy(update={"capex": 1000})
    # grid_updated = grid.model_copy(
    #     update={"grid_design": grid.grid_design.model_copy(update={"pole": new_grid_design_pole})}
    # )
    # print(f"grid_updated: {grid_updated}")

    # # Example of creating a list of nodes from the ground up:
    # node_1 = {
    #     "latitude": 40.6,
    #     "longitude": 0.323,
    #     "how_added": HowAdded.manual,
    #     "node_type": NodeType.consumer,
    #     "consumer_type": ConsumerType.household,
    #     "custom_specification": "",
    #     "shs_options": 0,
    #     "consumer_detail": ConsumerDetail.default,
    #     "is_connected": False,
    # }
    # node_2 = {
    #     "latitude": 40.59,
    #     "longitude": 0.339,
    #     "how_added": HowAdded.manual,
    #     "node_type": NodeType.power_house,
    #     "consumer_type": ConsumerType.na,
    #     "custom_specification": "",
    #     "shs_options": 0,
    #     "consumer_detail": ConsumerDetail.na,
    #     "is_connected": False,
    # }
    # node_dicts = [node_1, node_2]
    # nodes: NodeAttributes = NodeAttributes(
    #     latitude={i: node_dicts[i]["latitude"] for i in range(len(node_dicts))},  # type: ignore
    #     longitude={i: node_dicts[i]["longitude"] for i in range(len(node_dicts))},  # type: ignore
    #     how_added={i: node_dicts[i]["how_added"] for i in range(len(node_dicts))},  # type: ignore
    #     node_type={i: node_dicts[i]["node_type"] for i in range(len(node_dicts))},  # type: ignore
    #     consumer_type={i: node_dicts[i]["consumer_type"] for i in range(len(node_dicts))},  # type: ignore
    #     custom_specification={
    #         i: node_dicts[i]["custom_specification"]
    #         for i in range(len(node_dicts))  # type: ignore
    #     },
    #     shs_options={i: node_dicts[i]["shs_options"] for i in range(len(node_dicts))},  # type: ignore
    #     consumer_detail={i: node_dicts[i]["consumer_detail"] for i in range(len(node_dicts))},  # type: ignore
    #     is_connected={i: node_dicts[i]["is_connected"] for i in range(len(node_dicts))},  # type: ignore
    # )
    # print(f"nodes: {nodes}")

    # # Another option is to use pandas:
    # import pandas as pd

    # df = pd.DataFrame(
    #     {
    #         "latitude": [10.5, 10.7],
    #         "longitude": [20.1, 20.3],
    #         "how_added": ["automatic", "k-means"],
    #         "node_type": ["consumer", "pole"],
    #         "consumer_type": ["household", "n.a."],
    #         "custom_specification": ["none", "break-pole"],
    #         "shs_options": [0, 2],
    #         "consumer_detail": ["default", "n.a."],
    #         "is_connected": [True, False],
    #         "distance_to_load_center": [1.5, 2.3],
    #         "parent": [None, "0"],
    #         "distribution_cost": [10.0, 15.0],
    #     },
    #     index=[0, 1],  # node IDs
    # )
    # df.index = df.index.astype(int)  # type: ignore # Ensure index is int
    # fields = {col: df[col].to_dict() for col in df.columns}  # type: ignore
    # nodes_alt = NodeAttributes(**fields)  # type: ignore
    # print(f"nodes_alt: {nodes_alt}")

    # # And we can replace the original nodes in the example from file and print it with nodes
    # # JSON-encoded:
    # grid_updated_alt = grid.model_copy(update={"nodes": nodes_alt})
    # grid_updated_alt_encoded = GridDescriptorNodesEncoded.from_grid_descriptor(grid_updated_alt)
    # print(f"grid_updated_alt as JSON: {grid_updated_alt_encoded.model_dump_json()}")
