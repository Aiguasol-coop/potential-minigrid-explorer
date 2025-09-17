import fastapi
import sqlmodel
import geojson_pydantic as geopydantic
from geoalchemy2 import functions as geofunc
import sqlalchemy
from sqlalchemy.sql.elements import ColumnElement
from typing import Any
from geoalchemy2 import Geometry

import app.db.core as db
import app.service_offgrid_planner.demand as demand
import app.grid.domain as grid
import app.shared.bounding_box as bounding_box
import app.shared.geography as geography


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


class GridDistributionLineResponse(grid.GridDistributionLineBase, geography.HasLinestringAttribute):
    geography: geopydantic.LineString


####################################################################################################
###   FASTAPI PATH OPERATIONS   ####################################################################
####################################################################################################

# TODO: Import full centroids layer + recalculate road distance with new shp file.. + review
# existing minigrids layer.
router = fastapi.APIRouter()


@router.get("/buildings")
def get_buildings_by_bbox(
    db: db.Session, bbox: bounding_box.BoundingBox = fastapi.Query()
) -> list[BuildingResponse]:
    min_lon, min_lat, max_lon, max_lat = bbox.parts
    envelope = geofunc.ST_MakeEnvelope(min_lon, min_lat, max_lon, max_lat, 4326)
    centroid_geom: ColumnElement[Any] = sqlalchemy.cast(
        grid.Building.pg_geography_centroid, Geometry(geometry_type="POINT", srid=4326)
    )

    cluster_centroids: list[grid.Building] = list(
        db.exec(
            sqlmodel.select(grid.Building).where(geofunc.ST_Within(centroid_geom, envelope))
        ).all()
    )
    buildings: list[BuildingResponse] = []
    for building in cluster_centroids:
        building.building_type = (
            demand.get_keys_from_value(
                demand.CLASS_CONVERSION, f"{building.building_type}_{building.category.lower()}"
            )
            if building.building_type != "other" and building.category
            else "household"
        )
        buildings.append(BuildingResponse.model_validate(building))

    return buildings


@router.get("/roads")
def get_country_roads(
    db: db.Session,
    bbox: str | None = fastapi.Query(default=None),
) -> list[RoadsResponse]:
    query = sqlmodel.select(grid.Road)

    if bbox:
        min_lon, min_lat, max_lon, max_lat = bounding_box.BoundingBox(bbox=bbox).parts
        envelope = sqlalchemy.func.ST_MakeEnvelope(min_lon, min_lat, max_lon, max_lat, 4326)
        query = query.where(sqlalchemy.func.ST_Intersects(grid.Road.pg_geography, envelope))
    else:
        query = query.where(
            grid.Road.road_type.in_(  # type: ignore
                [
                    "motorway",
                    "trunk",
                    # "primary",
                    # "secondary",
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
    grid_network = db.exec(sqlmodel.select(grid.GridDistributionLine)).all()

    if not grid_network:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_404_NOT_FOUND, detail="No grid network found."
        )

    return [GridDistributionLineResponse.model_validate(line) for line in grid_network]
