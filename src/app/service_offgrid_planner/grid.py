import enum
import typing

import pydantic
import pydantic_core


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


ShsOptionsType = typing.TypeVar("ShsOptionsType")

ConsumerTypeType = typing.TypeVar("ConsumerTypeType")


class NodeAttributes(pydantic.BaseModel, typing.Generic[ShsOptionsType, ConsumerTypeType]):
    model_config = pydantic.ConfigDict(allow_inf_nan=True, ser_json_inf_nan="strings")

    # We use dicts instead of lists for easy fill up using an index
    latitude: dict[int, float] = pydantic.Field(default_factory=dict[int, float])
    longitude: dict[int, float] = pydantic.Field(default_factory=dict[int, float])
    how_added: dict[int, HowAdded] = pydantic.Field(default_factory=dict[int, HowAdded])
    node_type: dict[int, NodeType] = pydantic.Field(default_factory=dict[int, NodeType])
    consumer_type: dict[int, ConsumerTypeType] = pydantic.Field(
        default_factory=dict[int, ConsumerTypeType]
    )
    custom_specification: dict[int, CustomSpecification | None] = pydantic.Field(
        default_factory=dict[int, CustomSpecification | None]
    )

    shs_options: dict[int, ShsOptionsType | typing.Literal["NaN"]] = pydantic.Field(
        default_factory=dict[int, ShsOptionsType | typing.Literal["NaN"]]
    )
    """We represent NaN's with a string instead of a float, which is a bit hacky, but Postgres JSON
    type converts NaN to null, which makes round-trip impossible."""

    consumer_detail: dict[int, ConsumerDetail] = pydantic.Field(
        default_factory=dict[int, ConsumerDetail]
    )
    is_connected: dict[int, bool] = pydantic.Field(default_factory=dict[int, bool])

    distance_to_load_center: dict[int, ShsOptionsType | typing.Literal["NaN"]] | None = None
    """We represent NaN's with a string instead of a float, which is a bit hacky, but Postgres JSON
    type converts NaN to null, which makes round-trip impossible."""

    distribution_cost: dict[int, ShsOptionsType | typing.Literal["NaN"]] | None = None
    """We represent NaN's with a string instead of a float, which is a bit hacky, but Postgres JSON
    type converts NaN to null, which makes round-trip impossible."""

    parent: dict[int, str] | None = None

    @pydantic.field_serializer(
        "latitude",
        "longitude",
        "how_added",
        "node_type",
        "consumer_type",
        "custom_specification",
        "shs_options",
        "consumer_detail",
        "is_connected",
        "distance_to_load_center",
        "distribution_cost",
        "parent",
        mode="plain",
    )
    def dict_to_array(self, value: dict[int, typing.Any] | None) -> list[typing.Any] | None:
        if value is None:
            return None
        else:
            return [v for _k, v in sorted(value.items())]

    @pydantic.field_validator(
        "latitude",
        "longitude",
        "how_added",
        "node_type",
        "consumer_type",
        "custom_specification",
        "shs_options",
        "consumer_detail",
        "is_connected",
        "distance_to_load_center",
        "distribution_cost",
        "parent",
        mode="before",
    )
    @classmethod
    def array_to_dict(_cls, data: typing.Any) -> dict[int, typing.Any] | None:
        if isinstance(data, str | bytes | bytearray):
            # Assumed type for value: list[typing.Any] | None
            value = pydantic_core.from_json(data, allow_inf_nan=True)

            return {index: v for index, v in enumerate(value)} if value is not None else None
        elif isinstance(data, list):
            return {index: v for index, v in enumerate(data)}  # type: ignore
        else:
            return data

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
    nodes: NodeAttributes[float, ConsumerType]
    grid_design: GridDesign
    yearly_demand: float


class Links(pydantic.BaseModel):
    lat_from: list[str]
    lon_from: list[str]
    lat_to: list[str]
    lon_to: list[str]
    link_type: list[str]
    length: list[float]


class GridResult(pydantic.BaseModel):
    nodes: NodeAttributes[float | None, ConsumerType | None]
    links: Links


if __name__ == "__main__":
    nodes: NodeAttributes[float, ConsumerType] = NodeAttributes()
    nodes.distribution_cost = {}
    node_id = 0

    nodes.latitude[node_id] = 3.14
    nodes.longitude[node_id] = 2.7
    nodes.how_added[node_id] = HowAdded.automatic
    nodes.node_type[node_id] = NodeType.consumer
    nodes.consumer_type[node_id] = ConsumerType.household
    nodes.custom_specification[node_id] = ""  # Same value as in the example provided by RLI
    nodes.shs_options[node_id] = 0.0  # Same value as in the example provided by RLI
    nodes.consumer_detail[node_id] = ConsumerDetail.default
    nodes.is_connected[node_id] = True  # Same value as in the example provided by RLI
    nodes.distribution_cost[node_id] = "NaN"  # Same value as in the example provided by RLI

    print(nodes.model_dump())
    print("\n")
    print(nodes.model_dump_json())
