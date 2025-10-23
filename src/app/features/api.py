from typing import Any
import uuid

import fastapi
import pydantic
import sqlmodel
from geoalchemy2 import Geometry, shape
from geoalchemy2 import functions as geofunc
import geojson_pydantic as geopydantic
import shapely
import sqlalchemy
from sqlalchemy.sql.elements import ColumnElement
import math
import enum

import app.db.core as db
import app.service_offgrid_planner.demand as demand
import app.shared.bounding_box as bounding_box
import app.shared.geography as geography
import app.utils as utils
from app.features.domain import (
    GridDistributionLine,
    GridDistributionLineBase,
    MinigridStatus,
    MiniGrid,
    Road,
    Building,
)


####################################################################################################
###   MODELS AND DB ENTITIES   #####################################################################
####################################################################################################


class BuildingResponse(sqlmodel.SQLModel):
    building_type: str | None = None
    centroid_geography: geopydantic.Point


class RoadsResponse(sqlmodel.SQLModel):
    road_type: str | None = None
    length_km: float | None = None
    maxspeed: str | None = None
    geography: geopydantic.LineString


class GridDistributionLineResponse(GridDistributionLineBase, geography.HasLinestringAttribute):
    geography: geopydantic.LineString


class ExistingMinigrid(sqlmodel.SQLModel):
    id: pydantic.UUID4
    status: MinigridStatus
    name: str | None = None
    operator: str | None = None
    pv_capacity: float | None = None
    pv_estimated: bool | None = True
    distance_to_grid: float | None = None
    distance_to_road: float | None = None
    centroid: geopydantic.Point


####################################################################################################
###   FASTAPI PATH OPERATIONS   ####################################################################
####################################################################################################

# TODO: Import full centroids layer + recalculate road distance with new shp file.. + review

# existing minigrids layer.
router = fastapi.APIRouter()


class BadRequestBBOX(str, enum.Enum):
    bbox_size = "The selected area must not exceed approximately 10 km × 10 km."


@router.get("/buildings", responses={400: {"model": BadRequestBBOX}})
def get_buildings_by_bbox(
    db: db.Session,
    bbox: bounding_box.BoundingBox = fastapi.Query(
        description=(
            "Bounding box in the format: min_lat, min_lon, max_lat, max_lon. "
            "The selected area must not exceed approximately 10 km × 10 km."
        ),
        example="-13.675544, 40.382135,-13.630163, 40.468093",
    ),
) -> list[BuildingResponse]:
    min_lat, min_lon, max_lat, max_lon = bbox.parts

    # --- Compute approximate size of the bbox in kilometers ---
    # Longitude distance depends on latitude (cos(lat))
    avg_lat = (min_lat + max_lat) / 2.0
    lon_distance_km = (max_lon - min_lon) * 111.32 * math.cos(math.radians(avg_lat))
    lat_distance_km = (max_lat - min_lat) * 110.57

    if lon_distance_km > 10 or lat_distance_km > 10:
        raise fastapi.HTTPException(
            status_code=400,
            detail=(
                f"BBox too large: {lon_distance_km:.2f} km × {lat_distance_km:.2f} km. "
                f"{BadRequestBBOX.bbox_size.value}"
            ),
        )

    envelope = geofunc.ST_MakeEnvelope(min_lon, min_lat, max_lon, max_lat, 4326)
    centroid_geom: ColumnElement[Any] = sqlalchemy.cast(
        Building.pg_geography_centroid, Geometry(geometry_type="POINT", srid=4326)
    )

    cluster_centroids: list[Building] = list(
        db.exec(sqlmodel.select(Building).where(geofunc.ST_Within(centroid_geom, envelope))).all()
    )

    buildings: list[BuildingResponse] = []
    for building in cluster_centroids:
        building.building_type = (
            demand.get_keys_from_value(
                demand.CLASS_CONVERSION,
                f"{building.building_type}_{building.category.lower()}",
            )
            if building.building_type != "other" and building.category
            else "household"
        )
        buildings.append(BuildingResponse.model_validate(building))

    return buildings


@router.get("/roads")
def get_country_roads(
    db: db.Session,
    bbox: str | None = fastapi.Query(
        default=None,
        description="Optional bounding box to filter roads within a specific geographic area, "
        "in the format: min_lat, min_lon, max_lat, max_lon. "
        "Example: '-13.675544, 40.382135,-13.630163, 40.468093'. "
        "If provided, all road types within this area are returned. "
        "If omitted, only the main country roads are returned — ",
        example="-13.675544, 40.382135,-13.630163, 40.468093",
    ),
) -> list[RoadsResponse]:
    query = sqlmodel.select(Road)

    if bbox:
        min_lat, min_lon, max_lat, max_lon = bounding_box.BoundingBox(bbox=bbox).parts
        envelope = sqlalchemy.func.ST_MakeEnvelope(min_lon, min_lat, max_lon, max_lat, 4326)
        query = query.where(sqlalchemy.func.ST_Intersects(Road.pg_geography, envelope))
    else:
        query = query.where(
            Road.road_type.in_(  # type: ignore
                [
                    "motorway",
                    "trunk",
                    "trunk_link",
                    "primary",
                    "primary_link",
                    "secondary",
                    "secondary_link",
                    "tertiary",
                    "tertiary_link",
                ]
            )
        )

    roads = db.exec(query).all()
    if not roads:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_404_NOT_FOUND, detail="No roads found."
        )

    return [RoadsResponse.model_validate(road) for road in roads]


@router.get("/grid")
def get_grid_network(db: db.Session) -> list[GridDistributionLineResponse]:
    grid_network = db.exec(sqlmodel.select(GridDistributionLine)).all()

    if not grid_network:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_404_NOT_FOUND, detail="No grid network found."
        )

    return [GridDistributionLineResponse.model_validate(line) for line in grid_network]


@router.get("/minigrids")
def get_existing_minigrids(
    db: db.Session,
) -> list[ExistingMinigrid]:
    db_existing_minigrids = db.exec(sqlmodel.select(MiniGrid)).all()

    if not db_existing_minigrids:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_404_NOT_FOUND, detail="No existing minigrids found."
        )
    else:
        existing_minigrids: list[ExistingMinigrid] = [
            ExistingMinigrid(
                id=uuid.UUID(minigrid.id),
                status=minigrid.status,
                name=minigrid.name,
                operator=minigrid.operator,
                pv_capacity=minigrid.pv_power,
                pv_estimated=minigrid.estimated_power,
                distance_to_grid=minigrid.distance_to_grid / 1000.0
                if minigrid.distance_to_grid
                else None,  # Convert to km
                distance_to_road=minigrid.distance_to_road,
                centroid=minigrid.geography,
            )
            for minigrid in db_existing_minigrids
        ]

    return existing_minigrids


@router.post("/minigrids", status_code=fastapi.status.HTTP_201_CREATED)
def notify_existing_minigrid(db: db.Session, minigrid: ExistingMinigrid) -> utils.OkResponse:
    pt = shape.from_shape(  # type: ignore
        shapely.geometry.Point(
            minigrid.centroid.coordinates.longitude,  # type: ignore
            minigrid.centroid.coordinates.latitude,
        ),  # type: ignore
        srid=4326,
    )

    tol_meters = 1.0
    existing = db.exec(
        sqlmodel.select(MiniGrid).where(
            sqlalchemy.func.ST_DWithin(MiniGrid.pg_geography, pt, tol_meters)
        )
    ).first()

    if existing:
        raise fastapi.HTTPException(
            status_code=409, detail=f"Minigrid at same location already exists (id={existing.id})."
        )

    db_minigrid = MiniGrid(
        id=str(minigrid.id),
        name=minigrid.name,
        status=MinigridStatus(minigrid.status.value),
        operator=minigrid.operator,
        pv_power=minigrid.pv_capacity,
        estimated_power=minigrid.pv_estimated,
        distance_to_grid=minigrid.distance_to_grid * 1000.0
        if minigrid.distance_to_grid
        else None,  # Convert to m
        distance_to_road=minigrid.distance_to_road,
        pg_geography=geography._point_to_database(minigrid.centroid),  # type: ignore
    )

    db.add(db_minigrid)
    db.commit()
    db.refresh(db_minigrid)

    return utils.OkResponse(
        ok=True, message=f"Minigrids with uuid: {minigrid.id} notified successfully."
    )
