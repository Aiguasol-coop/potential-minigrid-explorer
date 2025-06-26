
import pydantic
import sqlmodel
import datetime
import uuid6
import random
import time
import os
import json
import requests

import app.db.core as db


class ExplorationNewResult(sqlmodel.SQLModel):
    id: pydantic.UUID6  # UUID4 is completely random, and this is what we want here.


class ExplorationParametersBase(sqlmodel.SQLModel):
    consumer_count_min: int = sqlmodel.Field(gt=30, default=100, le=500)

    diameter_max: float = sqlmodel.Field(gt=0.0, default=5000.0, le=10000.0)
    """Euclidean distance (units: meter) between the two most distant consumers."""

    distance_from_grid_min: float = sqlmodel.Field(ge=20000.0, default=60000.0, le=120000.0)
    """Units: meter."""

    match_distance_max: float = sqlmodel.Field(ge=100.0, default=5000.0, le=20000.0)
    """Potential minigrids that are at this distance or less of an already existing minigrid are
    filtered out. Units: meter."""


class ExplorationParameters(ExplorationParametersBase, table=True):

    id: str | None = sqlmodel.Field(
        default_factory=lambda: str(uuid6.uuid7()), primary_key=True, index=True
    )

    pid : str

    duration: datetime.timedelta | None
    num_of_minigrids: int | None


class ExplorationSimulationResult(sqlmodel.SQLModel, table=True):


def perform_search(db: db.Session, parameters : ExplorationParametersBase) -> ExplorationNewResult:

    start_time = time.time()

    # Initiate clustering process (start it on thread):
    id = uuid6.uuid7()
    pid = uuid6.uuid7()

    # Save search params and pid in DB
    process = ExplorationParameters.model_validate(parameters,
                    update = {'id': id,
                              'pid': pid})
    db.add(process)
    db.flush()

    # Store each sim id in db associated to the process.
    time.sleep(random.randint(1,3))
    num_of_minigrids = random.randint(2, 4)
    process.num_of_minigrids = num_of_minigrids
    db.flush()

    grid_opt = json.loads(os.path.join(os.getcwd(), 'src', 'test', 'examples', 'grid_opt_json.json'))
    supply_opt = json.loads(os.path.join(os.getcwd(), 'src', 'test', 'examples', 'supply_opt_json.json'))
    for minigrid in num_of_minigrids:

        # Request the supply run:
        supply_payload = {'json_file': supply_opt}
        supply_req = requests.post(url= 'https://optimizer-offgridplanner-app.apps2.rl-institut.de/uploadjson/supply',
                            params=supply_payload)


    # Store process duration
    end_time = time.time()
    process.duration = datetime.timedelta(end_time - start_time)
    db.flush()

    return ExplorationNewResult(id=id)
