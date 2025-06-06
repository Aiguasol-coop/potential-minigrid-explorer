import enum
import json
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


NodeParent = typing.Literal["unknown"] | str | None


class GridDesignComponent(pydantic.BaseModel):
    capex: float | None = None
    max_length: float | None = None
    epc: float | None = None
    max_n_connections: int | None = None
    connection_cost: float | None = None
    include: bool | None = None
    max_grid_cost: float | None = None


class GridDesign(pydantic.BaseModel):
    distribution_cable: GridDesignComponent
    connection_cable: GridDesignComponent
    pole: GridDesignComponent
    mg: GridDesignComponent
    shs: GridDesignComponent


class NodeAttributes(pydantic.BaseModel):
    latitude: dict[int, float]
    longitude: dict[int, float]
    how_added: dict[int, HowAdded]
    node_type: dict[int, NodeType]
    consumer_type: dict[int, ConsumerType]
    custom_specification: dict[int, CustomSpecification]
    shs_options: dict[int, ShsOptionsInt]
    consumer_detail: dict[int, ConsumerDetail]
    is_connected: dict[int, bool]
    distance_to_load_center: dict[int, float] | None = None
    parent: dict[int, NodeParent] | None = None
    distribution_cost: dict[int, float] | None = None

    @pydantic.model_validator(mode="after")
    def check_key_sets_match(self) -> "NodeAttributes":
        field_values: dict[str, dict[int, typing.Any]] = {
            field: value for field, value in self.__dict__.items() if isinstance(value, dict)
        }

        if not field_values:
            return self

        # Use first field as reference
        reference_field, reference_keys = next(iter(field_values.items()))
        for _field, keys in field_values.items():
            if set(keys.keys()) != set(reference_keys.keys()):
                mismatch_info = {
                    f: (len(k), sorted(set(k) - set(reference_keys)))
                    for f, k in field_values.items()
                    if set(k.keys()) != set(reference_keys.keys())
                }
                raise ValueError(
                    f"Inconsistent node ID keys across dict fields. "
                    f"Reference: {reference_field}. Mismatches: {mismatch_info}"
                )

        return self


class GridDescriptor(pydantic.BaseModel):
    nodes: NodeAttributes
    grid_design: GridDesign
    yearly_demand: float

    @pydantic.model_validator(mode="before")
    @classmethod
    def decode_nodes_if_needed(cls, data: typing.Any) -> dict[str, typing.Any]:
        if isinstance(data, GridDescriptor):
            return data.model_dump()

        if isinstance(data, GridDescriptorNodesEncoded):
            return {
                "nodes": NodeAttributes.model_validate(json.loads(data.nodes)),
                "grid_design": data.grid_design,
                "yearly_demand": data.yearly_demand,
            }

        if isinstance(data, dict):
            if isinstance(data["nodes"], str):
                data = data.copy()  # type: ignore
                data["nodes"] = NodeAttributes.model_validate(json.loads(data["nodes"]))

        return data  # type: ignore


class GridDescriptorNodesEncoded(pydantic.BaseModel):
    nodes: str  # JSON-encoded NodeAttributes
    grid_design: GridDesign
    yearly_demand: float

    @classmethod
    def from_grid_descriptor(cls, descriptor: GridDescriptor) -> typing.Self:
        return cls(
            nodes="".join(json.dumps(descriptor.nodes.model_dump(exclude_unset=True)).split()),
            grid_design=descriptor.grid_design,
            yearly_demand=descriptor.yearly_demand,
        )


if __name__ == "__main__":
    import pathlib

    json_string = pathlib.Path("./tests/examples/grid_opt_json.json").read_text()
    grid_nodes_encoded = GridDescriptorNodesEncoded.model_validate_json(json_string)
    grid = GridDescriptor.model_validate(grid_nodes_encoded)
    grid_nodes_encoded_again = GridDescriptorNodesEncoded.from_grid_descriptor(grid)

    assert grid_nodes_encoded.model_dump_json() == grid_nodes_encoded_again.model_dump_json()

    # Example of how to update some deeply nested field in the example (the capex for poles):
    new_grid_design_pole = grid.grid_design.pole.model_copy(update={"capex": 1000})
    grid_updated = grid.model_copy(
        update={"grid_design": grid.grid_design.model_copy(update={"pole": new_grid_design_pole})}
    )

    print(grid_updated)
