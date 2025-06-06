import datetime
import uuid

import fastapi

# import geojson
import pydantic
import sqlmodel


####################################################################################################
###   MODELS AND DB ENTITIES   #####################################################################
####################################################################################################


class ExplorationParameters(sqlmodel.SQLModel):
    consumer_count_min: int = sqlmodel.Field(gt=30, default=100, le=500)

    diameter_max: float = sqlmodel.Field(
        gt=0.0,
        default=5000.0,
        le=10000.0,
        description="""Euclidean distance (meters) between the two most distant consumers.""",
    )

    distance_from_grid_min: float = sqlmodel.Field(ge=20000.0, default=60000.0, le=120000.0)
    """Unit: meters."""

    # distance_from_road_min: float = sqlmodel.Field()

    # cluster_count_goal: int | None = sqlmodel.Field(
    #     gt=0,
    #     default=None,
    #     description="""Number of minigrids we want as the result of the clustering, prior to
    #                 filtering out the ones not fulfilling other requirements.""",
    # )


class ExplorationNewResult(sqlmodel.SQLModel):
    id: pydantic.UUID4  # UUID4 is completely random, and this is what we want here.


class ExplorationEstimationResult(sqlmodel.SQLModel):
    minigrid_count: int
    duration: datetime.timedelta


class ProjectDescriptor(sqlmodel.SQLModel):
    id: pydantic.UUID4
    consumer_count: int
    # diameter_max: float
    # connection_length: float
    distance_from_grid: float
    lcoe: float  # levelized cost of energy $/kWh
    capex: float  # capital expenditure $US
    res: float  # renewable energy share
    co2_savings: float  # CO2 emission savings in tones/year
    consumption_total: float  # total consumption in kWh/year
    coordinates: str
    # TODO: coordinates, in a PostGIS or offgridplanner compatible format.


class ExplorationRunning(sqlmodel.SQLModel):
    starting_time: datetime.datetime
    cluster_count: int
    minigrid_count: int


class ExplorationFinished(sqlmodel.SQLModel):
    starting_time: datetime.datetime
    duration: datetime.timedelta
    cluster_count: int
    minigrid_count: int
    exploration_result: list[ProjectDescriptor]


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
