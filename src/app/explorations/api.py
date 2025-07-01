import datetime
import decimal
import enum
import random
import uuid

import fastapi
import geoalchemy2
import geojson_pydantic as geopydantic
import pydantic
import sqlalchemy
import sqlmodel
import shapely

import app.db.core as db
import app.grid.domain as grid
import app.shared.geography as geography
import app.utils as utils
import app.explorations.domain as explorations

from app.explorations.domain import (
    ExplorationError,
    ExplorationParameters,
    start_exploration,
)


####################################################################################################
###   MODELS AND DB ENTITIES   #####################################################################
####################################################################################################


class ProjectStatus(enum.Enum):
    POTENTIAL = "potential"
    PROJECT = "project"
    MONITORING = "monitoring"


class ProjectStatusUpdate(pydantic.BaseModel):
    id: pydantic.UUID4
    status: ProjectStatus


class PotentialProject(sqlmodel.SQLModel):
    id: pydantic.UUID4
    status: ProjectStatus
    # TODO: Define list of "inputs" and "outputs/results" equal to RLI models


class ExplorationEstimationResult(sqlmodel.SQLModel):
    num_of_minigrids: int
    duration: datetime.timedelta


class PotentialMinigrid(sqlmodel.SQLModel):
    id: pydantic.UUID4

    region: str

    consumer_count: int

    diameter_max: float
    """Euclidean distance (units: meter) between the two most distant consumers."""

    distance_from_grid: float
    """Units: meter."""

    distance_from_road: float
    """Units: meter."""

    # TODO: in this field and the following, check and use the units returned by the optimizers.
    lcoe: float
    """Levelized cost of energy. Units: $/kWh."""

    capex: decimal.Decimal
    """Capital expenditure. Units: $US."""

    res: float = sqlmodel.Field(ge=0.0, le=100.0)
    """Renewable energy share."""

    co2_savings: float
    """CO2 emission savings. Units: tonne/year."""

    consumption_total: float
    """Total consumption. Units: kWh/year."""

    centroid: geopydantic.Point


class ExistingMinigrid(sqlmodel.SQLModel):
    id: pydantic.UUID7
    status: grid.MinigridStatus
    name: str | None = None
    operator: str | None = None
    pv_capacity: float | None = None
    pv_estimated: bool | None = True
    distance_to_grid: float | None = None
    distance_to_road: float | None = None
    centroid: geopydantic.Point


class GridDistributionLineResponse(grid.GridDistributionLineBase, geography.HasLinestringAttribute):
    geography: geopydantic.LineString


class ExplorationStatus(str, enum.Enum):
    RUNNING = "RUNNING"
    STOPPED = "STOPPED"
    FINISHED = "FINISHED"
    FAILED = "FAILED"


class ExplorationResult(sqlmodel.SQLModel):
    status: ExplorationStatus
    starting_time: datetime.datetime
    duration: datetime.timedelta
    clusters_found: int
    minigrids_found: int
    minigrids_analyzed: int
    minigrids: list[PotentialMinigrid]


class ResponseOk(pydantic.BaseModel):
    message: str = "Ok"


####################################################################################################
###   FASTAPI PATH OPERATIONS   ####################################################################
####################################################################################################


router = fastapi.APIRouter()


@router.get("/grid")
def get_grid_network(db: db.Session) -> list[GridDistributionLineResponse]:
    grid_network = db.exec(sqlmodel.select(grid.GridDistributionLine)).all()

    if not grid_network:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_404_NOT_FOUND, detail="No grid network found."
        )

    return grid_network


# TODO: Add get roads endpoints.
@router.get("/roads")
def get_country_roads(db: db.Session):
    return


@router.get("/existing")
def get_existing_minigrids(
    db: db.Session,
) -> list[ExistingMinigrid]:
    db_existing_minigrids = db.exec(sqlmodel.select(grid.MiniGrid)).all()

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


@router.post("/existing", status_code=fastapi.status.HTTP_201_CREATED)
def notify_existing_minigrids(db: db.Session, minigrid: ExistingMinigrid) -> utils.OkResponse:
    pt = geoalchemy2.shape.from_shape(  # type: ignore
        shapely.geometry.Point(
            minigrid.centroid.coordinates.longitude,  # type: ignore
            minigrid.centroid.coordinates.latitude,
        ),  # type: ignore
        srid=4326,
    )

    tol_meters = 1.0
    existing = db.exec(
        sqlmodel.select(grid.MiniGrid).where(
            sqlalchemy.func.ST_DWithin(grid.MiniGrid.pg_geography, pt, tol_meters)
        )
    ).first()

    if existing:
        raise fastapi.HTTPException(
            status_code=409, detail=f"Minigrid at same location already exists (id={existing.id})."
        )

    db_minigrid = grid.MiniGrid(
        id=str(minigrid.id),
        name=minigrid.name,
        status=grid.MinigridStatus(minigrid.status.value),
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


@router.post("/", status_code=fastapi.status.HTTP_201_CREATED)
def start_new_exploration(db: db.Session, parameters: ExplorationParameters) -> pydantic.UUID4:
    # TODO: Check there isn't already an exploration being run:

    db.exec(sqlmodel.delete(explorations.Simulation))  # type: ignore
    db.commit()

    id = start_exploration(db=db, parameters=parameters)
    if isinstance(id, ExplorationError):
        # TODO: raise HTTP error
        pass

    return id


@router.get("/{exploration_id}/estimation")
def get_exploration_estimation(exploration_id: pydantic.UUID6) -> ExplorationEstimationResult:
    # TODO: put some meaningful value here
    result = ExplorationEstimationResult(
        num_of_minigrids=random.randint(40, 90),
        duration=datetime.timedelta(random.randint(10, 120)),
    )

    return result


# @router.get("/{exploration_id}")
# def get_exploration_progress(exploration_id: pydantic.UUID4, offset: int) -> ExplorationResult:
#     """This endpoint is meant to be polled on.

#     The offset is on the list of returned analyzed minigrids.
#     """
#     # TODO: check exploration status

#     pass


# @router.get("/{exploration_id}/minigrids/{grid_id}/supply")
# def get_exploration_supply(
#     exploration_id: pydantic.UUID4, grid_id: pydantic.UUID4
# ) -> supply.SupplyDescriptor:
#     pass


# @router.get("/{exploration_id}/minigrids/{grid_id}/grid")
# def get_exploration_grid(
#     exploration_id: pydantic.UUID4, grid_id: pydantic.UUID4
# ) -> grid.GridDescriptor:
#     pass


@router.post("/{exploration_id}/stop")
def stop_exploration(id: pydantic.UUID4) -> ResponseOk:
    pass

    return ResponseOk()


@router.put("/{project_id}/update")
def update_project_status(id: pydantic.UUID4, status: ProjectStatus) -> ProjectStatusUpdate:
    # TODO: Get project from DB & update status.
    updated_project = ProjectStatusUpdate(id=id, status=status)

    return updated_project
