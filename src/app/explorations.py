import datetime
import typing
import uuid

import fastapi

# import geojson
import pydantic
import sqlmodel


####################################################################################################
###   MODELS AND DB ENTITIES   #####################################################################
####################################################################################################


class ExplorationParameters(sqlmodel.SQLModel):
    consumer_count_min: int = sqlmodel.Field(gt=0, default=30)

    consumer_count_max: int = sqlmodel.Field(gt=0, default=300)

    diameter_max: float = sqlmodel.Field(
        gt=0.0,
        default=2000,
        description="""Maximum euclidean distance (meters) between two consumers.""",
    )

    distance_from_grid_min: float = sqlmodel.Field(ge=20000.0, default=20000.0)

    # cluster_count_goal: int | None = sqlmodel.Field(
    #     gt=0,
    #     default=None,
    #     description="""Number of minigrids we want as the result of the clustering, prior to
    #                 filtering out the ones not fulfilling other requirements.""",
    # )

    @pydantic.model_validator(mode="after")
    def check_consumer_count_range(self) -> typing.Self:
        if self.consumer_count_min >= self.consumer_count_max:
            raise ValueError("consumer_count_min should be smaller than consumer_count_max")
        return self


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
