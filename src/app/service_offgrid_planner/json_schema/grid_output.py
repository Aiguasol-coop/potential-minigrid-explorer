# generated by datamodel-codegen:
#   filename:  https://optimizer-offgridplanner-app.apps2.rl-institut.de/schema/grid/output
#   timestamp: 2025-06-25T16:17:48+00:00

from __future__ import annotations

from pydantic import BaseModel


class Nodes(BaseModel):
    latitude: list[str]
    longitude: list[str]
    how_added: list[str]
    node_type: list[str]
    consumer_type: list[str]
    custom_specification: list[str | None]
    shs_options: list[int | None]
    consumer_detail: list[str]
    is_connected: list[bool]
    distance_to_load_center: list[float | None]
    parent: list[str]
    distribution_cost: list[float | None]


class Links(BaseModel):
    lat_from: list[str]
    lon_from: list[str]
    lat_to: list[str]
    lon_to: list[str]
    link_type: list[str]
    length: list[float]


class Model(BaseModel):
    nodes: Nodes
    links: Links
