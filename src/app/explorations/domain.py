import datetime
import enum
import threading
import time
import typing
import uuid

import pydantic
import sqlalchemy
import sqlalchemy.dialects.postgresql as sqlapostgres
import sqlmodel

import app.db.core as db
import app.service_offgrid_planner.grid as grid
import app.service_offgrid_planner.service as offgrid_planner
import app.service_offgrid_planner.supply as supply


class ExplorationParameters(sqlmodel.SQLModel):
    consumer_count_min: int = sqlmodel.Field(gt=30, default=100, le=500)

    diameter_max: float = sqlmodel.Field(gt=0.0, default=5000.0, le=10000.0)
    """Euclidean distance (units: meter) between the two most distant consumers."""

    distance_from_grid_min: float = sqlmodel.Field(ge=20000.0, default=60000.0, le=120000.0)
    """Units: meter."""

    match_distance_max: float = sqlmodel.Field(ge=100.0, default=5000.0, le=20000.0)
    """Potential minigrids that are at this distance or less of an already existing minigrid are
    filtered out. Units: meter."""


class Exploration(ExplorationParameters, table=True):
    id: pydantic.UUID4 = sqlmodel.Field(default_factory=uuid.uuid4, primary_key=True)

    minigrids_found: int | None = None

    clusters_found: int | None = None

    clusters_found_at: datetime.datetime | None = None

    optimizer_inputs_generated_at: datetime.datetime | None = None

    optimizer_finished_at: datetime.datetime | None = None

    created_at: datetime.datetime = sqlmodel.Field(default_factory=lambda: datetime.datetime.now())


class Simulation(sqlmodel.SQLModel, table=True):
    id: pydantic.UUID4 = sqlmodel.Field(default_factory=uuid.uuid4, primary_key=True)

    exploration_id: pydantic.UUID4 = sqlmodel.Field(foreign_key="exploration.id")

    cluster_id: int

    # WARNING: Be careful when updating the following attributes, read
    # https://amercader.net/blog/beware-of-json-fields-in-sqlalchemy/. Recommended action: use deep
    # copy (probably from pydantic), as explained at the end of the article.

    grid_input: dict[str, typing.Any] = sqlmodel.Field(
        sa_column=sqlalchemy.Column(sqlapostgres.JSONB)
    )

    grid_results: dict[str, typing.Any] | None = sqlmodel.Field(
        sa_column=sqlalchemy.Column(sqlapostgres.JSONB), default=None
    )

    supply_input: dict[str, typing.Any] = sqlmodel.Field(
        sa_column=sqlalchemy.Column(sqlapostgres.JSONB)
    )

    supply_results: dict[str, typing.Any] | None = sqlmodel.Field(
        sa_column=sqlalchemy.Column(sqlapostgres.JSONB), default=None
    )

    created_at: datetime.datetime = sqlmodel.Field(default_factory=lambda: datetime.datetime.now())

    __table_args__ = (
        sqlalchemy.UniqueConstraint(
            "exploration_id", "cluster_id", name="uc_exploration_id_cluster_id"
        ),
    )


class ExplorationError(str, enum.Enum):
    start_clustering_failed = "The clustering algorithm could not be launched"
    clustering_algorithm_failed = "The clustering algorithm failed"


class ClusterBuilding(sqlmodel.SQLModel):
    building_id: int  # shp_id
    building_type: str
    surface: float
    latitude: float
    longitude: float


class Cluster(sqlmodel.SQLModel):
    cluster_id: int
    latitude: float
    longitude: float
    province: str
    num_buildings: int
    distance_to_grid_m: float
    avg_distance_to_road_m: float
    avg_surface: float
    eps_meters: float
    diameter_km: float
    grid_distance_km: float
    buildings: list[ClusterBuilding]


class ClusteringResult(sqlmodel.SQLModel):
    clusters_found: int
    potential_minigrids: list[Cluster]


class WorkerFindClusters:
    def __init__(self, parameters: ExplorationParameters):
        self._parameters = parameters
        self._result: ClusteringResult | None = None

    def __call__(self) -> None:
        #  TODO: aquí el codi del Michel (DBSCAN)
        #
        ### BEGIN of FAKE code

        self._result = ClusteringResult(clusters_found=50, potential_minigrids=[])

        for i in range(10):
            c = Cluster(
                cluster_id=i,
                latitude=-10.0,
                longitude=-20.0,
                province="A_province",
                num_buildings=30,
                distance_to_grid_m=1200000,
                avg_distance_to_road_m=150000,
                avg_surface=40.5,
                eps_meters=20,
                diameter_km=0.3,
                grid_distance_km=1200,
                buildings=[],
            )
            self._result.potential_minigrids.append(c)

        ### END of FAKE code

    @property
    def result(self) -> ClusteringResult | None:
        return self._result


class WorkerGenerateOptimizerInputs:
    def __init__(
        self, db: db.Session, exploration_id: pydantic.UUID4, clustering_result: ClusteringResult
    ):
        self._db = db
        self._exploration_id = exploration_id
        self._clustering_result = clustering_result
        self._result: None | ExplorationError = None

    def __call__(self) -> None:
        db_exploration = self._db.get(Exploration, self._exploration_id)

        assert db_exploration

        db_exploration.clusters_found = self._clustering_result.clusters_found
        db_exploration.minigrids_found = len(self._clustering_result.potential_minigrids)
        self._db.add(db_exploration)
        self._db.commit()

        for cluster in self._clustering_result.potential_minigrids:
            # TODO: check global variable that finishes the thread if set

            grid_input, supply_input = self.generate_inputs(cluster)

            db_simulation = Simulation(
                exploration_id=self._exploration_id,
                cluster_id=cluster.cluster_id,
                grid_input=grid_input.model_dump(mode="json"),
                supply_input=supply_input.model_dump(mode="json"),
            )
            self._db.add(db_simulation)
            self._db.commit()

        self._result = None

    def generate_inputs(self, cluster: Cluster) -> tuple[grid.GridInput, supply.SupplyInput]:
        # TODO: codi del Michel aquí
        #
        ### BEGIN of FAKE code

        import pathlib

        input_json = pathlib.Path("./tests/examples/grid_input_example.json").read_text()
        grid_input = grid.GridInput.model_validate_json(input_json)
        input_json = pathlib.Path("./tests/examples/supply_input_example.json").read_text()
        supply_input = supply.SupplyInput.model_validate_json(input_json)

        ### END of FAKE code

        return (grid_input, supply_input)

    @property
    def result(self) -> None | ExplorationError:
        return self._result


class WorkerRunOptimizer:
    def __init__(self, db: db.Session, exploration_id: pydantic.UUID4):
        self._db = db
        self._exploration_id = exploration_id
        self._finished = False
        self._result: None | ExplorationError = None

    def __call__(self) -> None:
        NUM_SLOTS: int = 5
        slots: list[
            tuple[
                pydantic.UUID4 | None,
                offgrid_planner.CheckerGrid | None,
                offgrid_planner.CheckerSupply | None,
            ]
        ] = [(None, None, None) for _ in range(NUM_SLOTS)]
        statement = sqlmodel.select(Simulation).where(
            Simulation.exploration_id == self._exploration_id,
            Simulation.grid_results is None,
        )

        # Startup: fill up as many slots as possible with simulations
        db_simulations = self._db.exec(statement.limit(NUM_SLOTS)).all()
        for i, db_simulation in enumerate(db_simulations):
            grid_input = grid.GridInput.model_validate(db_simulation.grid_input)
            supply_input = supply.SupplyInput.model_validate(db_simulation.supply_input)
            checker_grid = offgrid_planner.optimize_grid(grid_input)
            checker_supply = offgrid_planner.optimize_supply(supply_input)

            # TODO: check errors
            assert not isinstance(
                checker_grid, offgrid_planner.ErrorServiceOffgridPlanner
            ) and not isinstance(checker_supply, offgrid_planner.ErrorServiceOffgridPlanner)

            slots[i] = (db_simulation.id, checker_grid, checker_supply)

        # Invariant: slots[] contains minigrids we have not finished running the simulation for,
        # yet. If the first value of the tuple is None, the other two are None as well.

        while not all(minigrid_id is None for minigrid_id, _g, _s in slots):
            # TODO: check global variable that finishes the thread if set
            time.sleep(1)

            for i, (minigrid_id, checker_grid, checker_supply) in enumerate(slots):
                # If the slot is empty, fill it up with a remaining simulation
                if not minigrid_id:
                    db_simulation = self._db.exec(statement.limit(1)).one_or_none()
                    if db_simulation:
                        grid_input = grid.GridInput.model_validate(db_simulation.grid_input)
                        supply_input = supply.SupplyInput.model_validate(db_simulation.supply_input)
                        checker_grid = offgrid_planner.optimize_grid(grid_input)
                        checker_supply = offgrid_planner.optimize_supply(supply_input)

                        # TODO: check errors
                        assert not isinstance(
                            checker_grid, offgrid_planner.ErrorServiceOffgridPlanner
                        ) and not isinstance(
                            checker_supply, offgrid_planner.ErrorServiceOffgridPlanner
                        )

                        slots[i] = (db_simulation.id, checker_grid, checker_supply)

                # Slot not empty: check if either the grid or the supply optimizers have finished
                else:
                    db_simulation = self._db.get(Simulation, minigrid_id)

                    assert db_simulation

                    if checker_grid:
                        grid_output = checker_grid()

                        # TODO: check errors
                        assert not isinstance(
                            grid_output, offgrid_planner.ErrorServiceOffgridPlanner
                        )

                        if grid_output.status == offgrid_planner.RequestStatus.DONE:
                            assert grid_output.results and not isinstance(
                                grid_output.results, offgrid_planner.ErrorResultType
                            )

                            db_simulation.grid_results = grid_output.results.model_dump(mode="json")
                            checker_grid = None
                            self._db.add(db_simulation)
                            self._db.commit()

                    if checker_supply:
                        supply_output = checker_supply()

                        # TODO: check errors
                        assert not isinstance(
                            supply_output, offgrid_planner.ErrorServiceOffgridPlanner
                        )

                        if supply_output.status == offgrid_planner.RequestStatus.DONE:
                            assert supply_output.results and not isinstance(
                                supply_output.results, offgrid_planner.ErrorResultType
                            )

                            # The following is type-safe because supply.ResultKey can be used
                            # wherever a str is expected:
                            db_simulation.supply_results = supply_output.results  # type: ignore
                            checker_supply = None
                            self._db.add(db_simulation)
                            self._db.commit()

                    # Empty the slot if the simulation has finished:
                    if not checker_grid and not checker_supply:
                        minigrid_id = None
                    slots[i] = minigrid_id, checker_grid, checker_supply

    @property
    def result(self) -> None | ExplorationError:
        return self._result


def worker_exploration(
    db: db.Session, parameters: ExplorationParameters, exploration_id: pydantic.UUID4
):
    """Worker to be used as the target of a thread. It creates 3 sub-threads and waits until all of
    them finish."""

    worker_clusters = WorkerFindClusters(parameters)
    thread_clusters = threading.Thread(target=worker_clusters, name=f"clusters/{exploration_id}")
    thread_clusters.start()
    thread_clusters.join()
    clustering_result = worker_clusters.result

    assert clustering_result

    db_exploration = db.get(Exploration, exploration_id)

    assert db_exploration

    db_exploration.clusters_found_at = datetime.datetime.now()
    db.add(db_exploration)
    db.commit()

    # The following 2 workers can run in parallel
    worker_inputs = WorkerGenerateOptimizerInputs(db, exploration_id, clustering_result)
    thread_inputs = threading.Thread(target=worker_inputs, name=f"inputs/{exploration_id}")
    thread_inputs.start()

    worker_results = WorkerRunOptimizer(db, exploration_id)
    thread_results = threading.Thread(target=worker_results, name=f"results/{exploration_id}")
    thread_results.start()

    thread_inputs.join()
    db_exploration.optimizer_inputs_generated_at = datetime.datetime.now()
    db.add(db_exploration)
    db.commit()

    thread_results.join()
    db_exploration.optimizer_finished_at = datetime.datetime.now()
    db.add(db_exploration)
    db.commit()


def get_thread_by_name(name: str) -> threading.Thread | None:
    for thread in threading.enumerate():
        if thread.name == name:
            return thread

    return None


def start_exploration(
    db: db.Session, parameters: ExplorationParameters
) -> pydantic.UUID4 | ExplorationError:
    db_exploration = Exploration.model_validate(parameters)
    db.add(db_exploration)
    db.commit()
    db.refresh(db_exploration)

    thread = threading.Thread(
        target=worker_exploration(db, parameters, db_exploration.id),
        name=f"exploration/{db_exploration.id}",
    )
    thread.start()

    # We don't wait until the thread finishes, we want to return asap
    return db_exploration.id


def stop_exploration(db: db.Session, exploration_id: pydantic.UUID4) -> None | ExplorationError:
    # TODO: set global, thread-safe variable that indicates to threads to kill themselves

    # TODO: delete all associated PotentialMinigrid in the DB
    return None


def check_exploration(
    db: db.Session, exploration_id: pydantic.UUID4
) -> tuple[Exploration, list[Simulation]] | ExplorationError:
    """Returns the input and results for all the simulations that have already finished in the
    current exploration."""

    # TODO: retrieve from the DB the current state of the current exploration and its simulations

    pass


if __name__ == "__main__":
    import app.db.core as db

    parameters = ExplorationParameters()

    with sqlmodel.Session(db.get_engine()) as session:
        start_exploration(session, parameters)
