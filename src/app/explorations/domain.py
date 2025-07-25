import datetime
import enum
import threading
import time
import json
import uuid
import typing

import pydantic
import sqlalchemy
import sqlalchemy.dialects
import sqlmodel
import geoalchemy2

import app.db.core as db
import app.service_offgrid_planner.grid as grid
import app.service_offgrid_planner.service as offgrid_planner
import app.service_offgrid_planner.supply as supply
import app.shared.geography as geography
import app.service_offgrid_planner.results as project_result


class ExplorationParameters(sqlmodel.SQLModel):
    consumer_count_min: int = sqlmodel.Field(gt=30, default=100, le=500)

    diameter_max: float = sqlmodel.Field(gt=0.0, default=5000.0, le=10000.0)
    """Euclidean distance (units: meter) between the two most distant consumers."""

    distance_from_grid_min: float = sqlmodel.Field(ge=20000.0, default=60000.0, le=120000.0)
    """Units: meter."""

    match_distance_max: float = sqlmodel.Field(ge=100.0, default=5000.0, le=20000.0)
    """Potential minigrids that are at this distance or less of an already existing minigrid are
    filtered out. Units: meter."""


class ExplorationStatus(str, enum.Enum):
    RUNNING = "RUNNING"
    FINISHED = "FINISHED"
    ERROR = "ERROR"
    STOPPED = "STOPPED"


class Exploration(ExplorationParameters, table=True):
    id: pydantic.UUID4 = sqlmodel.Field(default_factory=uuid.uuid4, primary_key=True)

    minigrids_found: int | None = None

    clusters_found: int | None = None

    clusters_found_at: datetime.datetime | None = None

    optimizer_inputs_generated_at: datetime.datetime | None = None

    optimizer_finished_at: datetime.datetime | None = None

    status: ExplorationStatus = sqlmodel.Field(
        default=ExplorationStatus.RUNNING,
        sa_column=sqlalchemy.Column(sqlalchemy.Enum(ExplorationStatus), nullable=False),
    )

    created_at: datetime.datetime = sqlmodel.Field(default_factory=lambda: datetime.datetime.now())


class ProjectStatus(enum.Enum):
    POTENTIAL = "POTENTIAL"
    PROJECT = "PROJECT"
    MONITORING = "MONITORING"


class SimulationStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    FINISHED = "FINISHED"
    STOPPED = "STOPPED"
    ERROR = "ERROR"
    PROCESSED_ERROR = "PROCESSED_ERROR"
    PROCESSED = "PROCESSED"


class Simulation(sqlmodel.SQLModel, table=True):
    id: pydantic.UUID4 = sqlmodel.Field(default_factory=uuid.uuid4, primary_key=True)

    exploration_id: pydantic.UUID4 = sqlmodel.Field(foreign_key="exploration.id")

    cluster_id: int

    # WARNING: Be careful when updating the following attributes, read
    # https://amercader.net/blog/beware-of-json-fields-in-sqlalchemy/. Recommended action: use deep
    # copy (probably from pydantic), as explained at the end of the article.

    project_input: str | None = sqlmodel.Field(
        sa_column=sqlalchemy.Column(sqlalchemy.Text), default=None
    )

    grid_input: str = sqlmodel.Field(sa_column=sqlalchemy.Column(sqlalchemy.Text))

    grid_results: str | None = sqlmodel.Field(
        sa_column=sqlalchemy.Column(sqlalchemy.Text), default=None
    )

    supply_input: str = sqlmodel.Field(sa_column=sqlalchemy.Column(sqlalchemy.Text))

    supply_results: str | None = sqlmodel.Field(
        sa_column=sqlalchemy.Column(sqlalchemy.Text), default=None
    )

    status: SimulationStatus = sqlmodel.Field(
        default=SimulationStatus.PENDING,
        sa_column=sqlalchemy.Column(sqlalchemy.Enum(SimulationStatus), nullable=False),
    )

    project_status: ProjectStatus = sqlmodel.Field(
        default=ProjectStatus.POTENTIAL,
        sa_column=sqlalchemy.Column(sqlalchemy.Enum(ProjectStatus), nullable=False),
    )

    created_at: datetime.datetime = sqlmodel.Field(default_factory=lambda: datetime.datetime.now())

    __table_args__ = (
        sqlalchemy.UniqueConstraint(
            "exploration_id", "cluster_id", name="uc_exploration_id_cluster_id"
        ),
    )


class ClusterBuilding(sqlmodel.SQLModel):
    building_id: int  # shp_id
    building_type: str
    surface: float
    latitude: float
    longitude: float


class ClusterBase(sqlmodel.SQLModel):
    cluster_id: int
    province: str
    num_buildings: int
    distance_to_grid_m: float
    avg_distance_to_road_m: float
    avg_surface: float
    eps_meters: float
    diameter_km: float
    grid_distance_km: float
    buildings: list[ClusterBuilding] = sqlmodel.Field(
        sa_column=sqlalchemy.Column(sqlalchemy.dialects.postgresql.JSONB, nullable=False),  # type: ignore
        default_factory=list,
    )
    lcoe: float | None = None
    """Levelized cost of energy. Units: $/kWh."""
    capex: float | None = None
    """Capital expenditure. Units: $US."""
    res: float | None = sqlmodel.Field(ge=0.0, le=100.0, default=None)
    """Renewable energy share."""
    co2_savings: float | None = None
    """CO2 emission savings. Units: tonne/year."""
    consumption_total: float | None = None
    """Total consumption. Units: kWh/year."""


class Cluster(ClusterBase, geography.HasPointColumn, table=True):
    id: pydantic.UUID4 | None = sqlmodel.Field(
        default_factory=lambda: str(uuid.uuid4()), primary_key=True, index=True
    )

    pg_geography: str = sqlmodel.Field(
        default=None,
        sa_column=sqlalchemy.Column(
            geoalchemy2.Geography(geometry_type="POINT", srid=4326), nullable=False
        ),
    )
    create_at: datetime.datetime = sqlmodel.Field(default_factory=lambda: datetime.datetime.now())


class ExplorationError(str, enum.Enum):
    start_clustering_failed = "The clustering algorithm could not be launched"
    clustering_algorithm_failed = "The clustering algorithm failed"


class ClusteringResult(sqlmodel.SQLModel):
    clusters_found: int
    potential_minigrids: list[Cluster]


class WorkerFindClusters:
    def __init__(self, parameters: ExplorationParameters, exploration_id: pydantic.UUID4):
        self._parameters = parameters
        self._exploration_id = exploration_id
        self._result: ClusteringResult | None = None
        self._db: db.Session = sqlmodel.Session(db.get_engine())

    def __call__(self) -> None:
        db_exploration = self._db.get(Exploration, self._exploration_id)

        assert db_exploration

        #  TODO: aquí el codi del Michel (DBSCAN)
        #
        ### BEGIN of FAKE code

        if db_exploration.status == ExplorationStatus.STOPPED:
            self._result = None
            return self._result

        self._result = ClusteringResult(clusters_found=50, potential_minigrids=[])

        for i in range(10):
            if db_exploration.status == ExplorationStatus.STOPPED:  # type: ignore
                self._result = None
                return self._result

            c = Cluster(
                cluster_id=i,
                province="A_province",
                num_buildings=30,
                distance_to_grid_m=1200000,
                avg_distance_to_road_m=150000,
                avg_surface=40.5,
                eps_meters=20,
                diameter_km=0.3,
                grid_distance_km=1200,
                buildings=[],
                pg_geography="POINT(2.0 41.0)",
            )
            self._result.potential_minigrids.append(c)
            self._db.add(c)
            self._db.commit()
            self._db.refresh(c)

        ### END of FAKE code

    @property
    def result(self) -> ClusteringResult | None:
        return self._result


class WorkerGenerateOptimizerInputs:
    def __init__(self, exploration_id: pydantic.UUID4, clustering_result: ClusteringResult):
        self._db: db.Session = sqlmodel.Session(db.get_engine())
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
        self._db.refresh(db_exploration)

        if db_exploration.status == ExplorationStatus.STOPPED:
            self._result = None
            return self._result

        for cluster in self._clustering_result.potential_minigrids:
            # TODO: check global variable that finishes the thread if set
            if db_exploration.status == ExplorationStatus.STOPPED:  # type: ignore
                self._result = None
                return self._result

            grid_input, supply_input = self.generate_inputs(cluster)

            db_simulation = Simulation(
                exploration_id=self._exploration_id,
                cluster_id=cluster.cluster_id,
                grid_input=grid_input.model_dump_json(),
                supply_input=supply_input.model_dump_json(),
            )
            self._db.add(db_simulation)
            self._db.commit()
            self._db.refresh(db_simulation)

        self._result = None

    def generate_inputs(self, cluster: Cluster) -> tuple[grid.GridInput, supply.SupplyInput]:
        # TODO: codi del Michel aquí
        #
        ### BEGIN of FAKE code

        import pathlib

        input_json = pathlib.Path("app/src/tests/examples/grid_input_example.json").read_text()
        grid_input = grid.GridInput.model_validate_json(input_json)
        input_json = pathlib.Path("app/src/tests/examples/supply_input_example.json").read_text()
        supply_input = supply.SupplyInput.model_validate_json(input_json)

        ### END of FAKE code

        return (grid_input, supply_input)

    @property
    def result(self) -> None | ExplorationError:
        return self._result


class WorkerRunOptimizer:
    def __init__(self, exploration_id: pydantic.UUID4):
        self._db: db.Session = sqlmodel.Session(db.get_engine())
        self._exploration_id = exploration_id
        self._finished = False
        self._result: None | ExplorationError = None

    def __call__(self) -> None:
        db_exploration = self._db.get(Exploration, self._exploration_id)

        assert db_exploration

        NUM_SLOTS: int = 3
        slots: list[
            tuple[
                pydantic.UUID4 | None,
                offgrid_planner.CheckerGrid | None,
                offgrid_planner.CheckerSupply | None,
            ]
        ] = [(None, None, None) for _ in range(NUM_SLOTS)]
        statement = sqlmodel.select(Simulation).where(
            Simulation.exploration_id == self._exploration_id,
            Simulation.status == SimulationStatus.PENDING,
        )

        # Wait until some simulations are available in the DB
        while (
            not self._db.exec(statement).all()
            and db_exploration.status != ExplorationStatus.STOPPED
        ):
            time.sleep(1)

        if db_exploration.status == ExplorationStatus.STOPPED:
            self._result = None
            return self._result

        # Startup: fill up as many slots as possible with simulations
        executed_simulations: int = 0
        last_bucket = False
        db_simulations = self._db.exec(statement.limit(NUM_SLOTS)).all()
        for i, db_simulation in enumerate(db_simulations):
            
            time.sleep(3)
            
            if db_exploration.status == ExplorationStatus.STOPPED:  # type: ignore
                self._result = None
                return self._result

            grid_input = grid.GridInput.model_validate(json.loads(db_simulation.grid_input))
            supply_input = supply.SupplyInput.model_validate(json.loads(db_simulation.supply_input))
            checker_grid = offgrid_planner.optimize_grid(grid_input)
            checker_supply = offgrid_planner.optimize_supply(supply_input)

            db_simulation.status = SimulationStatus.RUNNING
            self._db.add(db_simulation)
            self._db.commit()
            self._db.refresh(db_simulation)

            # TODO: check errors
            if isinstance(checker_grid, offgrid_planner.ErrorServiceOffgridPlanner) | isinstance(
                checker_supply, offgrid_planner.ErrorServiceOffgridPlanner
            ):
                db_simulation.status = SimulationStatus.ERROR
                self._db.add(db_simulation)
                self._db.commit()
                self._db.refresh(db_simulation)

                executed_simulations += 1
            else:
                if not isinstance(
                    checker_grid, offgrid_planner.ErrorServiceOffgridPlanner
                ) and not isinstance(checker_supply, offgrid_planner.ErrorServiceOffgridPlanner):
                    slots[i] = (db_simulation.id, checker_grid, checker_supply)

        # Invariant: slots[] contains minigrids we have not finished running the simulation for,
        # yet. If the first value of the tuple is None, the other two are None as well.
        if not db_exploration.minigrids_found:
            raise RuntimeError(
                "The exploration has no minigrids to run simulations for. "
                "Please check the clustering step."
            )

        while (
            not all(minigrid_id is None for minigrid_id, _g, _s in slots)
            or executed_simulations < db_exploration.minigrids_found
            and not db_exploration.status == ExplorationStatus.STOPPED  # type: ignore
        ):
            # TODO: check global variable that finishes the thread if set
            time.sleep(1)

            for i, (minigrid_id, checker_grid, checker_supply) in enumerate(slots):
                
                time.sleep(3)
                
                if db_exploration.status == ExplorationStatus.STOPPED:  # type: ignore
                    self._result = None
                    return self._result

                # TODO: I think this can be deleted!
                # If the slot is empty, fill it up with a remaining simulation
                if not minigrid_id and not last_bucket:
                    db_simulation = self._db.exec(statement.limit(1)).one_or_none()
                    if db_simulation and db_simulation.id not in [s[0] for s in slots]:
                        grid_input = grid.GridInput.model_validate(
                            json.loads(db_simulation.grid_input)
                        )
                        supply_input = supply.SupplyInput.model_validate(
                            json.loads(db_simulation.supply_input)
                        )
                        checker_grid = offgrid_planner.optimize_grid(grid_input)
                        checker_supply = offgrid_planner.optimize_supply(supply_input)

                        db_simulation.status = SimulationStatus.RUNNING
                        self._db.add(db_simulation)
                        self._db.commit()
                        self._db.refresh(db_simulation)

                        # TODO: check errors
                        if isinstance(
                            checker_grid, offgrid_planner.ErrorServiceOffgridPlanner
                        ) | isinstance(checker_supply, offgrid_planner.ErrorServiceOffgridPlanner):
                            db_simulation.status = SimulationStatus.ERROR
                            self._db.add(db_simulation)
                            self._db.commit()
                            self._db.refresh(db_simulation)

                            executed_simulations += 1
                        else:
                            if not isinstance(
                                checker_grid, offgrid_planner.ErrorServiceOffgridPlanner
                            ) and not isinstance(
                                checker_supply, offgrid_planner.ErrorServiceOffgridPlanner
                            ):
                                slots[i] = (db_simulation.id, checker_grid, checker_supply)

                # Slot not empty: check if either the grid or the supply optimizers have finished
                else:
                    if not minigrid_id:
                        continue

                    if db_exploration.status == ExplorationStatus.STOPPED:  # type: ignore
                        self._result = None
                        return self._result

                    db_simulation = self._db.get(Simulation, minigrid_id)

                    assert db_simulation

                    if checker_grid:
                        grid_output = checker_grid()

                        # TODO: check errors
                        if isinstance(grid_output, offgrid_planner.ErrorServiceOffgridPlanner):
                            db_simulation.status = SimulationStatus.ERROR
                            self._db.add(db_simulation)
                            self._db.commit()
                            self._db.refresh(db_simulation)

                            checker_grid = None
                            grid_output = None

                        if grid_output and grid_output.status == offgrid_planner.RequestStatus.DONE:
                            assert grid_output.results and not isinstance(
                                grid_output.results, offgrid_planner.ErrorResultType
                            )

                            db_simulation.grid_results = grid_output.results.model_dump_json()
                            checker_grid = None
                            self._db.add(db_simulation)
                            self._db.commit()
                            self._db.refresh(db_simulation)

                    if checker_supply:
                        supply_output = checker_supply()

                        # TODO: check errors
                        if isinstance(supply_output, offgrid_planner.ErrorServiceOffgridPlanner):
                            db_simulation.status = SimulationStatus.ERROR
                            self._db.add(db_simulation)
                            self._db.commit()
                            self._db.refresh(db_simulation)

                            checker_supply = None
                            supply_output = None

                        if (
                            supply_output
                            and supply_output.status == offgrid_planner.RequestStatus.DONE
                        ):
                            assert supply_output.results and not isinstance(
                                supply_output.results, offgrid_planner.ErrorResultType
                            )

                            # The following is type-safe because supply.ResultKey can be used
                            # wherever a str is expected:
                            db_simulation.supply_results = supply_output.results.model_dump_json()
                            checker_supply = None
                            self._db.add(db_simulation)
                            self._db.commit()
                            self._db.refresh(db_simulation)

                    # Empty the slot if the simulation has finished:
                    if not checker_grid and not checker_supply:
                        minigrid_id = None
                        executed_simulations += 1
                        db_simulation.status = (
                            SimulationStatus.FINISHED
                            if db_simulation.status == SimulationStatus.RUNNING
                            else db_simulation.status
                        )
                        self._db.add(db_simulation)
                        self._db.commit()
                        self._db.refresh(db_simulation)

                    slots[i] = minigrid_id, checker_grid, checker_supply

            # Check if there are simulations pending:
            if (
                all(minigrid_id is None for minigrid_id, _g, _s in slots)
                and executed_simulations < db_exploration.minigrids_found
                and not db_exploration.status == ExplorationStatus.STOPPED  # type: ignore
            ):
                statement = sqlmodel.select(Simulation).where(
                    Simulation.exploration_id == self._exploration_id,
                    Simulation.status == SimulationStatus.PENDING,
                )
                NUM_SIM = min(NUM_SLOTS, db_exploration.minigrids_found - executed_simulations)
                db_simulations = self._db.exec(statement.limit(NUM_SIM)).all()
                for i, db_simulation in enumerate(db_simulations):
                    
                    time.sleep(3)
                    
                    grid_input = grid.GridInput.model_validate(json.loads(db_simulation.grid_input))
                    supply_input = supply.SupplyInput.model_validate(
                        json.loads(db_simulation.supply_input)
                    )
                    checker_grid = offgrid_planner.optimize_grid(grid_input)
                    checker_supply = offgrid_planner.optimize_supply(supply_input)
                    db_simulation.status = SimulationStatus.RUNNING

                    # TODO: check errors
                    if isinstance(
                        checker_grid, offgrid_planner.ErrorServiceOffgridPlanner
                    ) | isinstance(checker_supply, offgrid_planner.ErrorServiceOffgridPlanner):
                        db_simulation.status = SimulationStatus.ERROR
                        self._db.add(db_simulation)
                        self._db.commit()
                        self._db.refresh(db_simulation)

                        executed_simulations += 1
                    else:
                        if not isinstance(
                            checker_grid, offgrid_planner.ErrorServiceOffgridPlanner
                        ) and not isinstance(
                            checker_supply, offgrid_planner.ErrorServiceOffgridPlanner
                        ):
                            slots[i] = (db_simulation.id, checker_grid, checker_supply)

                if db_exploration.minigrids_found - executed_simulations <= NUM_SLOTS:
                    last_bucket = True

    @property
    def result(self) -> None | ExplorationError:
        return self._result


class WorkerProcessSimulationResults:
    def __init__(self, exploration_id: pydantic.UUID4):
        self._db: db.Session = sqlmodel.Session(db.get_engine())
        self._exploration_id = exploration_id
        self._result: None | ExplorationError = None

    def __call__(self) -> None:
        db_exploration = self._db.get(Exploration, self._exploration_id)

        assert db_exploration

        statement = sqlmodel.select(Simulation).where(
            Simulation.exploration_id == self._exploration_id,
            sqlmodel.or_(
                Simulation.status == SimulationStatus.FINISHED,
                Simulation.status == SimulationStatus.ERROR,
            ),
        )

        # Wait until some simulations are available in the DB
        while (
            not self._db.exec(statement).all()
            and db_exploration.status != ExplorationStatus.STOPPED
        ):
            time.sleep(1)

        num_processed = 0

        if db_exploration.minigrids_found is None:
            raise RuntimeError(
                "The exploration has no minigrids to run simulations for. "
                "Please check the clustering step."
            )

        if db_exploration.status == ExplorationStatus.STOPPED:
            self._result = None
            return self._result

        while (
            num_processed < db_exploration.minigrids_found
            and not db_exploration.status == ExplorationStatus.STOPPED  # type:ignore
        ):  # type: ignore
            simulations_to_process = self._db.exec(statement).all()

            for simulation in simulations_to_process:
                if db_exploration.status == ExplorationStatus.STOPPED:  # type: ignore
                    self._result = None
                    return self._result

                if simulation.status == SimulationStatus.FINISHED:
                    sim_results = self.process_simulation_results(simulation)
                    cluster = self._db.exec(
                        sqlmodel.select(Cluster).where(Cluster.cluster_id == simulation.cluster_id)
                    ).one()
                    assert cluster
                    updates = sim_results.model_dump(exclude_none=True)
                    for field, val in updates.items():
                        setattr(cluster, field, val)

                    self._db.add(cluster)
                    self._db.commit()
                    self._db.refresh(cluster)
                    simulation.status = SimulationStatus.PROCESSED
                    self._db.add(simulation)
                    self._db.commit()
                    self._db.refresh(simulation)
                    num_processed += 1

                elif simulation.status == SimulationStatus.ERROR:
                    simulation.status = SimulationStatus.PROCESSED_ERROR
                    self._db.add(simulation)
                    self._db.commit()
                    self._db.refresh(simulation)
                    num_processed += 1

    def _project_inputs(self) -> dict[str, typing.Any]:
        ProjectKeys: list[str] = ["n_days", "interest_rate", "tax", "lifetime"]
        ProjectJson: dict[str, typing.Any] = {}
        for key in ProjectKeys:
            value = getattr(self.project, key)
            ProjectJson.update({key: value})

        return ProjectJson

    def process_simulation_results(self, simulation: Simulation) -> project_result.ResultsSummary:
        self.project = project_result.Project(id=simulation.id)
        grid_input = grid.GridInput.model_validate_json(simulation.grid_input)
        self.project.grid_inputs = grid_input
        self.project.load_grid_inputs()

        supply_input = supply.SupplyInput.model_validate_json(simulation.supply_input)
        self.project.supply_inputs = supply_input
        self.project.load_supply_inputs()

        if simulation.grid_results:
            grid_output = grid.GridResult.model_validate_json(simulation.grid_results)
            self.project.grid_outputs = grid_output

        if simulation.supply_results:
            supply_output = supply.SupplyResult.model_validate_json(simulation.supply_results)
            self.project.supply_outputs = supply_output

        self.project.grid_results()
        self.project.supply_results()

        simulation.project_input = json.dumps(self._project_inputs())

        return self.project.get_results_summary()


def worker_exploration(parameters: ExplorationParameters, exploration_id: pydantic.UUID4):
    """Worker to be used as the target of a thread. It creates 3 sub-threads and waits until all of
    them finish."""

    with sqlmodel.Session(db.get_engine()) as db_session:
        worker_clusters = WorkerFindClusters(parameters, exploration_id)
        thread_clusters = threading.Thread(
            target=worker_clusters, name=f"clusters/{exploration_id}"
        )
        thread_clusters.start()
        thread_clusters.join()
        clustering_result = worker_clusters.result

        assert clustering_result

        db_exploration = db_session.get(Exploration, exploration_id)

        assert db_exploration

        db_exploration.clusters_found_at = datetime.datetime.now()
        db_session.add(db_exploration)
        db_session.commit()

        # The following 2 workers can run in parallel
        worker_inputs = WorkerGenerateOptimizerInputs(exploration_id, clustering_result)
        thread_inputs = threading.Thread(target=worker_inputs, name=f"inputs/{exploration_id}")
        thread_inputs.start()

        worker_optimizer = WorkerRunOptimizer(exploration_id)
        thread_optimizer = threading.Thread(
            target=worker_optimizer, name=f"optimizer/{exploration_id}"
        )
        thread_optimizer.start()

        worker_results = WorkerProcessSimulationResults(exploration_id)
        thread_results = threading.Thread(target=worker_results, name=f"results/{exploration_id}")
        thread_results.start()

        thread_inputs.join()
        db_exploration.optimizer_inputs_generated_at = datetime.datetime.now()
        db_session.add(db_exploration)
        db_session.commit()

        thread_optimizer.join()
        db_exploration.optimizer_finished_at = datetime.datetime.now()
        db_session.add(db_exploration)
        db_session.commit()

        thread_results.join()
        db_exploration.status = (
            ExplorationStatus.FINISHED
            if not all(
                simulation.status == SimulationStatus.PROCESSED_ERROR
                for simulation in db_session.exec(
                    sqlmodel.select(Simulation).where(Simulation.exploration_id == exploration_id)
                ).all()
            )
            else ExplorationStatus.ERROR
        )
        db_session.add(db_exploration)
        db_session.commit()


def get_thread_by_name(name: str) -> threading.Thread | None:
    for thread in threading.enumerate():
        if thread.name == name:
            return thread

    return None


def start_exploration(
    db: db.Session, parameters: ExplorationParameters
) -> pydantic.UUID4 | ExplorationError:
    db_exploration = Exploration.model_validate(parameters)
    db_exploration.status = ExplorationStatus.RUNNING
    db.add(db_exploration)
    db.commit()
    db.refresh(db_exploration)

    if db_exploration.status != ExplorationStatus.STOPPED:  # type: ignore
        thread = threading.Thread(
            target=worker_exploration,
            args=(parameters, db_exploration.id),
            name=f"exploration/{db_exploration.id}",
        )
        thread.start()

    # We don't wait until the thread finishes, we want to return asap
    return db_exploration.id


if __name__ == "__main__":
    import app.db.core as db

    parameters = ExplorationParameters()

    with sqlmodel.Session(db.get_engine()) as session:
        start_exploration(session, parameters)
