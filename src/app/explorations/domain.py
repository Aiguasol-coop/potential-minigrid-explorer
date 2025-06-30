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
import app.service_offgrid_planner.supply as supply


type ExplorationId = pydantic.UUID4


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
    id: ExplorationId = sqlmodel.Field(default_factory=uuid.uuid4, primary_key=True)

    minigrids_found: int | None = None

    clusters_found: int | None = None

    clusters_found_at: datetime.datetime | None = None

    optimizer_inputs_generated_at: datetime.datetime | None = None

    optimizer_finished_at: datetime.datetime | None = None

    created_at: datetime.datetime = sqlmodel.Field(default_factory=lambda: datetime.datetime.now())


type PotentialMinigridId = pydantic.UUID4


class PotentialMinigrid(sqlmodel.SQLModel, table=True):
    id: PotentialMinigridId = sqlmodel.Field(default_factory=uuid.uuid4, primary_key=True)

    exploration_id: ExplorationId = sqlmodel.Field(foreign_key="exploration.id")

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


def get_thread_by_name(name: str) -> threading.Thread | None:
    for thread in threading.enumerate():
        if thread.name == name:
            return thread

    return None


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
        ### START of fake FAKE code

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

        ### END of fake FAKE code

    @property
    def result(self) -> ClusteringResult | None:
        return self._result


class WorkerGenerateOptimizerInputs:
    def __init__(
        self, db: db.Session, exploration_id: ExplorationId, clustering_result: ClusteringResult
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
            grid_input, supply_input = self.generate_inputs(cluster)

            db_minigrid = PotentialMinigrid(
                exploration_id=self._exploration_id,
                cluster_id=cluster.cluster_id,
                grid_input=grid_input.model_dump(),
                supply_input=supply_input.model_dump(),
            )
            self._db.add(db_minigrid)
            self._db.commit()

        self._result = None

    def generate_inputs(self, cluster: Cluster) -> tuple[grid.GridInput, supply.SupplyInput]:
        # TODO: codi del Michel aquí
        #
        ### START of fake FAKE code

        import pathlib

        input_json = pathlib.Path("./tests/examples/grid_input_example.json").read_text()
        grid_input = grid.GridInput.model_validate_json(input_json)
        input_json = pathlib.Path("./tests/examples/supply_input_example.json").read_text()
        supply_input = supply.SupplyInput.model_validate_json(input_json)

        ### END of fake code

        return (grid_input, supply_input)

    @property
    def result(self) -> None | ExplorationError:
        return self._result


class WorkerRunOptimizer:
    def __init__(self, db: db.Session, exploration_id: ExplorationId):
        self._db = db
        self._exploration_id = exploration_id
        self._finished = False
        self._result: None | ExplorationError = None

    def __call__(self) -> None:
        thread_clustering = get_thread_by_name(f"clustering/{self._exploration_id}")
        if not thread_clustering:
            self._result = ExplorationError.clustering_algorithm_failed

            return

        while thread_clustering.is_alive():
            time.sleep(5)

        while not self._finished:
            time.sleep(0.200)
            update_simulation(self._db, self._exploration_id)

        self._result = None

    @property
    def result(self) -> None | ExplorationError:
        return self._result


def worker_exploration(
    db: db.Session, parameters: ExplorationParameters, exploration_id: ExplorationId
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


def start_exploration(
    db: db.Session, parameters: ExplorationParameters
) -> ExplorationId | ExplorationError:
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
    thread_clusters = get_thread_by_name(f"clusters/{exploration_id}")
    if thread_clusters:
        # TODO: set a variable in the thread so it kills itself.
        pass
    thread_inputs = get_thread_by_name(f"inputs/{exploration_id}")
    if thread_inputs:
        # TODO: set a variable in the thread so it kills itself.
        pass
    thread_results = get_thread_by_name(f"results/{exploration_id}")
    if thread_results:
        # TODO: set a variable in the thread so it kills itself.
        pass
    thread_exploration = get_thread_by_name(f"exploration/{exploration_id}")
    if thread_exploration:
        # TODO: set a variable in the thread so it kills itself.
        pass

    # TODO: delete all associated PotentialMinigrid in the DB
    return None


def check_exploration(db: db.Session, exploration_id: pydantic.UUID4) -> None | ExplorationError:
    pass
