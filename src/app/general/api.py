import fastapi
import sqlmodel
import geojson_pydantic as geopydantic
from geoalchemy2 import functions as geofunc
import sqlalchemy
from sqlalchemy.sql.elements import ColumnElement
from typing import Any
from geoalchemy2 import Geometry
import enum

import app._version
import app.db.core as db
import app.service_offgrid_planner.demand as demand
import app.grid.domain as grid
from app.explorations.domain import (PublicServiceData,
                                     HouseholdData,
                                     EnterpriseData,
                                     HouseholdHourlyProfile)

router = fastapi.APIRouter()

####################################################################################################
###   MODELS AND DB ENTITIES   #####################################################################
####################################################################################################

class BuildingResponse(sqlmodel.SQLModel):
    building_type: str | None = None
    centroid_geography: geopydantic.Point


class HouseHoldDataResponse(sqlmodel.SQLModel):
    subcategory: str
    kwh_per_day: float
    distribution: float


class HouseHoldProfileResponse(sqlmodel.SQLModel):
    subcategory: str
    hourly_profile: dict[str, float]


class AreaType(enum.Enum):
    isolated = "isolated"
    periurban = "periurban"

####################################################################################################
###   FASTAPI PATH OPERATIONS   ####################################################################
####################################################################################################

@router.get("/")
async def root():
    return {"message": "Hello from the potential-minigrid-explorer API service!"}


@router.get("/version")
async def version():
    return {"version": f"{app._version.__version__}"}


@router.get("/enterprise_categories")
def enterprise_categories(db:db.Session) -> list[str]:

    categories : list[str] = list(db.exec(sqlmodel.select(EnterpriseData.subcategory).distinct().order_by(EnterpriseData.subcategory)).all())

    return categories


@router.get("/public_service_categories")
def public_service_categories(db:db.Session) -> list[str]:

    categories : list[str] = list(db.exec(sqlmodel.select(PublicServiceData.subcategory).distinct().order_by(PublicServiceData.subcategory)).all())

    return categories


@router.get("/household_categories")
def household_categories(db:db.Session, area_type:AreaType) -> list[HouseHoldDataResponse]:

    categories : list[HouseholdData] = list(db.exec(sqlmodel.select(HouseholdData).where(HouseholdData.area_type == area_type)).all())

    return [HouseHoldDataResponse.model_validate(cat) for cat in categories]


@router.get("/household_profiles")
def household_profiles(db:db.Session, area_type:AreaType) -> list[HouseHoldProfileResponse]:

    profiles : list[HouseholdHourlyProfile] = list(db.exec(sqlmodel.select(HouseholdHourlyProfile).where(HouseholdHourlyProfile.area_type == area_type)).all())

    return [HouseHoldProfileResponse.model_validate(profile) for profile in profiles]


@router.post("/buildings")
def get_buildings_by_bbox(db: db.Session, bbox: tuple[float, float, float, float]) -> list[BuildingResponse]:

    min_lon, min_lat, max_lon, max_lat = bbox
    envelope = geofunc.ST_MakeEnvelope(min_lon, min_lat, max_lon, max_lat, 4326)
    centroid_geom : ColumnElement[Any] = sqlalchemy.cast(grid.Building.pg_geography_centroid, Geometry(geometry_type="POINT", srid=4326))

    cluster_centroids : list[grid.Building] = list(db.exec(sqlmodel.select(grid.Building).where(geofunc.ST_Within(centroid_geom, envelope))).all())
    buildings : list[BuildingResponse] = []
    for building in cluster_centroids:
        building.building_type = demand.get_keys_from_value(demand.CLASS_CONVERSION, f'{building.building_type}_{building.category.lower()}') if building.building_type != 'other' and building.category else 'household'
        buildings.append(BuildingResponse.model_validate(building))

    return buildings
