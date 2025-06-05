import collections.abc
import enum
import json
import typing

import pydantic


class HowAdded(str, enum.Enum):
    automatic = "automatic"
    k_means = "k-means"


class NodeType(str, enum.Enum):
    consumer = "consumer"
    power_house = "power-house"


class ConsumerType(str, enum.Enum):
    household = "household"
    na = "n.a."


class ConsumerDetail(str, enum.Enum):
    default = "default"
    na = "n.a."


ShsOptionsInt = typing.Annotated[int, pydantic.Field(ge=0, le=0)]


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
    latitude: dict[str, float]
    longitude: dict[str, float]
    how_added: dict[str, HowAdded]
    node_type: dict[str, NodeType]
    consumer_type: dict[str, ConsumerType]
    custom_specification: dict[str, str]
    shs_options: dict[str, ShsOptionsInt]
    consumer_detail: dict[str, ConsumerDetail]
    is_connected: dict[str, bool]
    distance_to_load_center: dict[str, float] | None = None
    parent: dict[str, str | None] | None = None
    distribution_cost: dict[str, float] | None = None

    @pydantic.model_validator(mode="after")
    def validate_consistent_node_keys(self) -> "NodeAttributes":
        key_sets = {
            field: set(getattr(self, field).keys())
            for field in self.model_fields
            if (_value := getattr(self, field)) is not None
        }

        # Check if all sets of keys are equal
        all_key_sets = list(key_sets.values())
        if not all(
            len(k) == len(all_key_sets[0]) and k == all_key_sets[0] for k in all_key_sets[1:]
        ):
            mismatch_info = {field: len(keys) for field, keys in key_sets.items()}
            raise ValueError(f"Inconsistent node ID keys across fields: {mismatch_info}")

        return self


class GridDescriptor(pydantic.BaseModel):
    nodes: str | None = None  # TODO: try to change to str | NodeAttributes
    grid_design: GridDesign
    yearly_demand: float

    # Internal property for use in Python
    nodes_decoded: NodeAttributes = pydantic.Field(exclude=True)

    @pydantic.model_validator(mode="before")
    @classmethod
    def parse_nodes_json(cls, data: typing.Any) -> typing.Any:
        if isinstance(data, dict) and "nodes" in data:
            raw_nodes = data["nodes"]  # type: ignore
            if isinstance(raw_nodes, str):
                data["nodes_decoded"] = NodeAttributes.model_validate(json.loads(raw_nodes))
            elif isinstance(
                raw_nodes, dict
            ):  # support internal creation with parsed NodeAttributes
                data["nodes_decoded"] = NodeAttributes.model_validate(raw_nodes)
                data["nodes"] = json.dumps(raw_nodes)
        return data  # type: ignore

    @pydantic.model_serializer(mode="wrap")
    def serialize_with_nodes(
        self, handler: collections.abc.Callable[[typing.Any], dict[str, typing.Any]]
    ) -> dict[str, typing.Any]:
        d = handler(self)
        d["nodes"] = json.dumps(self.nodes_decoded.model_dump())
        return d


if __name__ == "__main__":
    import pathlib

    json_string = pathlib.Path("./tests/examples/grid_opt_json.json").read_text()
    grid = GridDescriptor.model_validate_json(json_string)
    print(grid.model_dump())
