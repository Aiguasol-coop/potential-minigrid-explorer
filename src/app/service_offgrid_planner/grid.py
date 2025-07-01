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


ShsOptionsType = typing.TypeVar("ShsOptionsType")


class NodeAttributes(pydantic.BaseModel, typing.Generic[ShsOptionsType]):
    model_config = pydantic.ConfigDict(allow_inf_nan=True)

    latitude: list[float]
    longitude: list[float]
    how_added: list[HowAdded]
    node_type: list[NodeType]
    consumer_type: list[ConsumerType]
    custom_specification: list[CustomSpecification | None]
    shs_options: list[ShsOptionsType | None]
    consumer_detail: list[ConsumerDetail]
    is_connected: list[bool]
    distance_to_load_center: list[ShsOptionsType | None] | None = None
    distribution_cost: list[ShsOptionsType | None] | None = None
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
    nodes: NodeAttributes[float]
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
    nodes: NodeAttributes[float | None]
    links: Links
