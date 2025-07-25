import datetime
import enum

import geoalchemy2
import sqlalchemy
import sqlmodel
import uuid6

import app.shared.geography as geography


class GridDistributionLineBase(sqlmodel.SQLModel):
    status: str | None = None
    vltg_kv: float | None = None
    classes: str | None = None
    province: str | None = None
    length_km: float | None = None


class GridDistributionLine(GridDistributionLineBase, geography.HasLinestringColumn, table=True):
    __tablename__ = "grid_distribution_lines"  # type: ignore

    id: str | None = sqlmodel.Field(
        default_factory=lambda: str(uuid6.uuid7()), primary_key=True, index=True
    )

    id_shp: float | None = None

    pg_geography: str = sqlmodel.Field(
        default=None,
        sa_column=sqlalchemy.Column(
            geoalchemy2.Geography(geometry_type="LINESTRING", srid=4326), nullable=False
        ),
    )
    create_at: datetime.datetime = sqlmodel.Field(default_factory=lambda: datetime.datetime.now())


class MinigridStatus(str, enum.Enum):
    potential = "potential"
    planning = "planning"
    monitoring = "monitoring"
    known_to_exist = "known_to_exist"


class MiniGridBase(sqlmodel.SQLModel):
    status: MinigridStatus
    name: str | None = None
    province: str | None = None
    operator: str | None = None
    pv_power: float | None = None
    pv_power_units: str | None = None
    estimated_power: bool | None = None
    num_buildings: int | None = None
    max_building_distance: float | None = None
    distance_to_grid: float | None = None
    start_date: datetime.datetime | None = None
    distance_to_road: float | None = sqlmodel.Field(default=None)
    island: bool | None = sqlmodel.Field(default=None)


class MiniGrid(MiniGridBase, geography.HasPointColumn, table=True):
    __tablename__ = "mini_grids"  # type: ignore

    id: str | None = sqlmodel.Field(
        default_factory=lambda: str(uuid6.uuid7()), primary_key=True, index=True
    )

    pg_geography: str = sqlmodel.Field(
        default=None,
        sa_column=sqlalchemy.Column(
            geoalchemy2.Geography(geometry_type="POINT", srid=4326), nullable=False
        ),
    )
    create_at: datetime.datetime = sqlmodel.Field(default_factory=lambda: datetime.datetime.now())


class BuildingBase(sqlmodel.SQLModel):
    province: str | None = None
    electric_demand: float | None = None
    has_electricity: bool | None = None
    category: str | None = None
    building_type: str | None = None
    surface: float | None = None
    distance_to_grid: float | None = None
    distance_to_road: float | None = sqlmodel.Field(default=None)
    is_island: bool | None = sqlmodel.Field(default=None)


class Building(BuildingBase, geography.HasPointAndMultipolygonColumn, table=True):
    __tablename__ = "buildings"  # type: ignore

    id: str | None = sqlmodel.Field(
        default_factory=lambda: str(uuid6.uuid7()), primary_key=True, index=True
    )
    id_shp: int | None = sqlmodel.Field(
        default=None, sa_column=sqlalchemy.Column(sqlalchemy.BigInteger)
    )

    pg_geography_centroid: str = sqlmodel.Field(
        default=None,
        sa_column=sqlalchemy.Column(
            geoalchemy2.Geography(geometry_type="POINT", srid=4326), nullable=True
        ),
    )
    pg_geography: str = sqlmodel.Field(
        default=None,
        sa_column=sqlalchemy.Column(
            geoalchemy2.Geography(geometry_type="MULTIPOLYGON", srid=4326), nullable=True
        ),
    )
    create_at: datetime.datetime = sqlmodel.Field(default_factory=lambda: datetime.datetime.now())
