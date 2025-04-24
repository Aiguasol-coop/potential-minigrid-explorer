import uuid

import fastapi
import pydantic
import sqlmodel

from enum import Enum


####################################################################################################
###   MODELS AND DB ENTITIES   #####################################################################
####################################################################################################


class ProjectStatus(Enum):
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


####################################################################################################
###   FASTAPI PATH OPERATIONS   ####################################################################
####################################################################################################


router = fastapi.APIRouter()


@router.get("/{project_id}/results")
def get_project_results(id: pydantic.UUID4) -> PotentialProject:
    # TODO: Get project from DB & return all values.
    results = PotentialProject(id=uuid.uuid4(), status=ProjectStatus.POTENTIAL)

    return results


@router.put("/{project_id}/update")
def update_project_status(id: pydantic.UUID4, status: ProjectStatus) -> ProjectStatusUpdate:
    # TODO: Get project from DB & update status.
    updated_project = ProjectStatusUpdate(id=id, status=status)

    return updated_project
