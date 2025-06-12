import datetime
import decimal
import enum
import uuid

import fastapi
import geojson_pydantic as geopydantic
import pydantic
import sqlmodel


####################################################################################################
###   MODELS AND DB ENTITIES   #####################################################################
####################################################################################################


class ExplorationParameters(sqlmodel.SQLModel):
    consumer_count_min: int = sqlmodel.Field(gt=30, default=100, le=500)

    diameter_max: float = sqlmodel.Field(gt=0.0, default=5000.0, le=10000.0)
    """Euclidean distance (units: meter) between the two most distant consumers."""

    distance_from_grid_min: float = sqlmodel.Field(ge=20000.0, default=60000.0, le=120000.0)
    """Units: meter."""

    match_distance_max: float = sqlmodel.Field(ge=100.0, default=5000.0, le=20000.0)
    """Potential minigrids that are at this distance or less of an already existing minigrid are
    filtered out. Units: meter."""


class ExplorationNewResult(sqlmodel.SQLModel):
    id: pydantic.UUID4  # UUID4 is completely random, and this is what we want here.


class ExplorationEstimationResult(sqlmodel.SQLModel):
    minigrid_count: int
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


class MinigridStatus(str, enum.Enum):
    potential = "potential"
    planning = "planning"
    monitoring = "monitoring"
    known_to_exist = "known_to_exist"


class ExistingMinigrid(sqlmodel.SQLModel):
    id: pydantic.UUID4
    status: MinigridStatus

    # TODO: if the planner stores a polygon, they can send it.
    centroid: geopydantic.Point


class ExplorationRunning(sqlmodel.SQLModel):
    starting_time: datetime.datetime
    cluster_count: int
    minigrid_count: int


class ExplorationFinished(sqlmodel.SQLModel):
    starting_time: datetime.datetime
    duration: datetime.timedelta
    cluster_count: int
    minigrid_count: int
    exploration_result: list[PotentialMinigrid]


# TODO: exploration cancelled


class ExplorationFailed(sqlmodel.SQLModel):
    starting_time: datetime.datetime
    duration: datetime.timedelta
    error_message: str


type ExplorationProgress = ExplorationRunning | ExplorationFinished | ExplorationFailed


####################################################################################################
###   FASTAPI PATH OPERATIONS   ####################################################################
####################################################################################################


router = fastapi.APIRouter()


@router.post("/existing_minigrids")
def notify_existing_minigrids(minigrids: list[ExistingMinigrid]) -> None:
    pass


@router.post("/new", status_code=fastapi.status.HTTP_201_CREATED)
def start_new_exploration(parameters: ExplorationParameters) -> ExplorationNewResult:
    # TODO: send job to the queue.

    result = ExplorationNewResult(id=uuid.uuid4())

    return result


@router.get("/{exploration_id}/estimation")
def get_exploration_estimation(id: pydantic.UUID4) -> ExplorationEstimationResult:
    # TODO: put some meaningful value here
    result = ExplorationEstimationResult(minigrid_count=0, duration=datetime.timedelta(0))

    return result


@router.get("/{exploration_id}/progress")
def get_exploration_progress(id: pydantic.UUID4) -> ExplorationProgress:
    # TODO: check exploration status

    result = ExplorationRunning(
        starting_time=datetime.datetime.now(), cluster_count=0, minigrid_count=0
    )

    return result


@router.delete("/{exploration_id}")
def cancel_exploration(id: pydantic.UUID4):
    result = ExplorationNewResult(id=uuid.uuid4())

    return result
