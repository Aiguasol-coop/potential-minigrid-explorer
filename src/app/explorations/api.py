import datetime

import fastapi
import geojson_pydantic as geopydantic
import pydantic
import sqlmodel

import app.db.core as db
import app.explorations.domain as explorations

from app.explorations.domain import (
    ExplorationError,
    ExplorationParameters,
    start_exploration,
    stop_exploration,
    Exploration,
    Simulation,
    Cluster,
    SimulationStatus,
    ExplorationStatus,
    ProjectStatus,
)

# TODO: Review all models make consistent and review field values and units
####################################################################################################
###   MODELS AND DB ENTITIES   #####################################################################
####################################################################################################


class PotentialMinigridStatusUpdate(pydantic.BaseModel):
    id: pydantic.UUID4
    status: ProjectStatus


class PotentialMinigrid(sqlmodel.SQLModel):
    id: pydantic.UUID4
    status: ProjectStatus
    project_input: str | None
    grid_input: str | None
    supply_input: str | None
    grid_results: str | None
    supply_results: str | None


class PotentialMinigridResults(sqlmodel.SQLModel):
    id: pydantic.UUID4

    province: str

    num_buildings: int

    distance_to_grid_m: float
    """Euclidean distance (units: meter) between the two most distant consumers."""

    distance_from_grid: float
    """Units: meter."""

    avg_distance_to_road_m: float
    """Units: meter."""

    # TODO: in this field and the following, check and use the units returned by the optimizers.
    lcoe: float | None
    """Levelized cost of energy. Units: $/kWh."""

    capex: float | None
    """Capital expenditure. Units: $US."""

    res: float | None = sqlmodel.Field(ge=0.0, le=100.0)
    """Renewable energy share."""

    co2_savings: float | None
    """CO2 emission savings. Units: tonne/year."""

    consumption_total: float | None
    """Total consumption. Units: kWh/year."""

    centroid: geopydantic.Point | None


class ExplorationResult(sqlmodel.SQLModel):
    status: ExplorationStatus
    starting_time: datetime.datetime
    current_duration: str | None = None
    estimated_duration: str | None = None
    clusters_found: int | None = None
    minigrids_found: int | None = None
    minigrids_analyzed: int | None = None
    minigrids_calculated: int | None = None
    minigrids_aborted: int | None = None
    minigrids: list[PotentialMinigridResults] | None = None


class ResponseOk(pydantic.BaseModel):
    message: str = "Ok"


####################################################################################################
###   FASTAPI PATH OPERATIONS   ####################################################################
####################################################################################################

# TODO: Review and document known errors.
router = fastapi.APIRouter()


@router.post("/", status_code=fastapi.status.HTTP_201_CREATED)
def start_new_exploration(db: db.Session, parameters: ExplorationParameters) -> pydantic.UUID4:
    """Start a new exploration with the given parameters."""

    db_exploration_running = db.exec(
        sqlmodel.select(explorations.Exploration).where(
            explorations.Exploration.status == explorations.ExplorationStatus.RUNNING
        )
    ).first()
    if db_exploration_running:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_409_CONFLICT,
            detail=f"""An exploration with ID {db_exploration_running.id} is already running;
            please stop it or wait until it finishes.""",
        )

    db.exec(sqlmodel.delete(explorations.Cluster))  # type: ignore
    db.exec(sqlmodel.delete(explorations.Simulation))  # type: ignore
    db.commit()

    # TODO: Add error handling..
    id = start_exploration(db=db, parameters=parameters)
    if isinstance(id, ExplorationError):
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_400_BAD_REQUEST,
            detail=f"Error starting exploration: {id}",
        )

    return id


@router.get("/{exploration_id}")
def get_exploration_progress(
    db: db.Session, exploration_id: pydantic.UUID4
) -> ExplorationResult:  # offset: int
    """This endpoint is meant to be polled on.

    The offset is on the list of returned analyzed minigrids.
    """

    stmt = (
        sqlmodel.select(Exploration, Simulation, Cluster)
        .outerjoin(
            Simulation,
            sqlmodel.and_(
                Simulation.exploration_id == Exploration.id,  # type: ignore
                Simulation.status == SimulationStatus.PROCESSED,  # type: ignore
            ),
        )
        .outerjoin(
            Cluster,
            Cluster.cluster_id == Simulation.cluster_id,  # type: ignore
        )
        .where(
            Exploration.id == exploration_id,
        )
    )

    db_tuples = db.exec(stmt).all()

    if not db_tuples:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_404_NOT_FOUND,
            detail=f"Exploration with ID {exploration_id} not found or no minigrids processed yet.",
        )

    potential_minigrids: list[PotentialMinigridResults] = []
    for _, db_simulation, db_cluster in db_tuples:
        if db_simulation and db_cluster:
            potential_minigrids.append(
                PotentialMinigridResults(
                    id=db_simulation.id,
                    province=db_cluster.province,
                    num_buildings=db_cluster.num_buildings,
                    distance_to_grid_m=db_cluster.diameter_km,
                    distance_from_grid=db_cluster.grid_distance_km,
                    avg_distance_to_road_m=db_cluster.avg_distance_to_road_m,
                    lcoe=db_cluster.lcoe,
                    capex=db_cluster.capex,
                    res=db_cluster.res,
                    co2_savings=db_cluster.co2_savings,
                    consumption_total=db_cluster.consumption_total,
                    centroid=db_cluster.geography,
                )
            )

    db_simulations = db.exec(
        sqlmodel.select(Simulation).where(Simulation.exploration_id == exploration_id)
    ).all()

    num_calculated = 0
    num_aborted = 0
    for db_simulation in db_simulations:
        if db_simulation.status == SimulationStatus.PROCESSED:
            num_calculated += 1
        elif (
            db_simulation.status == SimulationStatus.ERROR
            or db_simulation.status == SimulationStatus.STOPPED
        ):
            num_aborted += 1

    db_exploration = db_tuples[0][0]

    remaining_minigrids = (
        db_exploration.minigrids_found - (num_calculated + num_aborted)
        if db_exploration.minigrids_found
        else 0
    )

    return ExplorationResult(
        status=db_exploration.status,
        starting_time=db_exploration.created_at,
        current_duration=str(db_exploration.optimizer_finished_at - db_exploration.created_at)
        if db_exploration.optimizer_finished_at
        else str(datetime.datetime.now() - db_exploration.created_at),
        estimated_duration=str(db_exploration.optimizer_finished_at - db_exploration.created_at)
        if db_exploration.optimizer_finished_at
        else str(
            datetime.datetime.now()
            - db_exploration.created_at
            + datetime.timedelta(minutes=3) * remaining_minigrids
        ),  # TODO: Estimate duration based on previous runs.
        clusters_found=db_exploration.clusters_found,
        minigrids_found=db_exploration.minigrids_found,
        minigrids_analyzed=num_calculated + num_aborted,
        minigrids_calculated=num_calculated,
        minigrids_aborted=num_aborted,
        minigrids=potential_minigrids,
    )


@router.get("/{exploration_id}/minigrids/{potential_minigrid_id}")
def get_exploration_files(
    db: db.Session, exploration_id: pydantic.UUID4, potential_minigrid_id: pydantic.UUID4
) -> PotentialMinigrid:
    db_simulation = db.exec(
        sqlmodel.select(Simulation).where(
            Simulation.id == potential_minigrid_id, Simulation.exploration_id == exploration_id
        )
    ).one_or_none()

    if not db_simulation:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_404_NOT_FOUND,
            detail=f"""Simulation with ID {potential_minigrid_id}
            not found in exploration with ID {exploration_id}""",
        )

    result: PotentialMinigrid = PotentialMinigrid(
        id=db_simulation.id,
        status=ProjectStatus.POTENTIAL,
        project_input=db_simulation.project_input,
        grid_input=db_simulation.grid_input,
        supply_input=db_simulation.supply_input,
        grid_results=db_simulation.grid_results,
        supply_results=db_simulation.supply_results,
    )

    return PotentialMinigrid.model_validate(result)


@router.post("/{exploration_id}/stop")
def stop_current_exploration(db: db.Session, exploration_id: pydantic.UUID4) -> ResponseOk:
    db_exploration = db.exec(
        sqlmodel.select(Exploration).where(Exploration.id == exploration_id)
    ).one_or_none()

    if not db_exploration:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_404_NOT_FOUND,
            detail=f"Exploration with ID {exploration_id} not found.",
        )

    if db_exploration.status != ExplorationStatus.RUNNING:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_409_CONFLICT,
            detail=f"Exploration with ID {exploration_id} is not running.",
        )

    stop_exploration(db, db_exploration.id)

    return ResponseOk()
