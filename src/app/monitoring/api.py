import fastapi
from pydantic import BaseModel
import geojson_pydantic as geopydantic
import datetime
import enum
import sqlmodel

import app.settings
import app.db.core as db
from app.monitoring.sds_client import SDSClient
from app.monitoring.utils import build_table, build_alarms
from app.monitoring.domain import AlarmType
from app.monitoring.domain import MonitoringMinigrid
from app.shared import geography

####################################################################################################
###   MODELS AND DB ENTITIES   #####################################################################
####################################################################################################


class MinigridDailyKPIS(BaseModel):
    consumption_kwh_day: float | None = None
    generation_kwh_day: float | None = None
    charged_kwh_day: float | None = None
    discharged_kwh_day: float | None = None
    self_consumption_kwh_day: float | None = None


class MonitoringMinigridResponse(BaseModel):
    id: str | None = None
    component_uuid: str
    name: str
    timezone: str
    status: str
    stale: bool
    last_update: datetime.datetime | None
    new_alarms: int = 0
    open_alarms: int = 0
    kpis: MinigridDailyKPIS
    centroid: geopydantic.Point | None
    monitoring_url: str | None


class MonitoringAlarm(BaseModel):
    id: str | None = None
    component_uuid: str
    name: str
    title: str
    description: str
    device: str | None
    status: AlarmType
    severity: str | None
    created_at: datetime.datetime
    updated_at: datetime.datetime


####################################################################################################
###   FASTAPI PATH OPERATIONS   ####################################################################
####################################################################################################


router = fastapi.APIRouter()


@router.get("/data", response_model=list[MonitoringMinigridResponse])
async def get_monitoring_data(
    db: db.Session,
) -> list[MonitoringMinigridResponse]:
    monitoring_settings = app.settings.get_settings()

    client = SDSClient(
        base_url=monitoring_settings.sds_base_url,
        api_key=monitoring_settings.sds_api_key,
        timeout_s=60,
    )

    df = build_table(client, monitoring_settings)

    # Write JSON outputs for the future web UI
    mini_grids = [
        MonitoringMinigridResponse.model_validate(
            {
                **r.to_dict(),
                "kpis": MinigridDailyKPIS(
                    consumption_kwh_day=r["consumption_kwh_day"],
                    generation_kwh_day=r["generation_kwh_day"],
                    charged_kwh_day=r["charged_kwh_day"],
                    # add other fields if needed
                ),
            }
        )
        for _, r in df.iterrows()
    ]

    # Get and match id from the DB MonitoringMinigrid table to add it to the response (if exists)
    for mg in mini_grids:
        db_entry = db.exec(
            sqlmodel.select(MonitoringMinigrid).where(MonitoringMinigrid.uuid == mg.component_uuid)
        ).first()
        if db_entry:
            mg.id = db_entry.id

    return mini_grids


@router.get("/alarms", response_model=list[MonitoringAlarm])
async def get_monitoring_alarms(
    db: db.Session,
) -> list[MonitoringAlarm]:
    monitoring_settings = app.settings.get_settings()

    client = SDSClient(
        base_url=monitoring_settings.sds_base_url,
        api_key=monitoring_settings.sds_api_key,
        timeout_s=60,
    )

    raw_alarms = build_alarms(client)

    alarms = [MonitoringAlarm.model_validate(r) for r in raw_alarms]

    for alarm in alarms:
        db_entry = db.exec(
            sqlmodel.select(MonitoringMinigrid).where(
                MonitoringMinigrid.uuid == alarm.component_uuid
            )
        ).first()
        if db_entry:
            alarm.id = db_entry.id

    return alarms


class BadRequest(str, enum.Enum):
    already_used_minigrid_id = (
        "The provided minigrid_id is already associated with a monitoring entry."
    )
    already_used_monitoring_id = "The provided monitoring_id already exists in the database."
    non_existing_monitoring_id = (
        "The provided monitoring_id does not exist in the monitoring platform."
    )


@router.get("/id_validation", responses={400: {"model": BadRequest}})
async def validate_id(db: db.Session, monitoring_id: str, minigrid_id: str) -> bool:
    # Check first if minigrid_id has already a monitoring_id associated in the DB.
    already_exist = db.exec(
        sqlmodel.select(MonitoringMinigrid).where(MonitoringMinigrid.id == minigrid_id)
    ).all()

    if already_exist:
        raise fastapi.HTTPException(
            status_code=400,
            detail=f"Minigrid {minigrid_id} already has a monitoring association.",
        )

    # Check if the monitoring_id exists in the DB
    monitoring_entry = db.exec(
        sqlmodel.select(MonitoringMinigrid).where(MonitoringMinigrid.uuid == monitoring_id)
    ).first()

    if monitoring_entry:
        raise fastapi.HTTPException(
            status_code=400,
            detail=f"Monitoring entry {monitoring_id} already exists in the DB.",
        )

    # Check if monitoring_id exists in the SDS data:
    client = SDSClient(
        base_url=app.settings.get_settings().sds_base_url,
        api_key=app.settings.get_settings().sds_api_key,
        timeout_s=60,
    )
    components = client.list_components()
    if not any(c["uuid"] == monitoring_id for c in components):
        raise fastapi.HTTPException(
            status_code=400,
            detail=f"""Monitoring entry {monitoring_id} does not exist in the monitoring platform...
            please create it first and then link it to the minigrid.""",
        )

    # Save the association in the DB
    for comp in components:
        if comp["uuid"] == monitoring_id:
            break

    minigrid = MonitoringMinigrid(
        id=minigrid_id,
        uuid=monitoring_id,
        name=comp.get("name"),  # type: ignore
        provider=comp.get("provider"),  # type: ignore
        typology=comp.get("typology"),  # type: ignore
        timezone=comp.get("timezone"),  # type: ignore
        address=comp.get("address"),  # type: ignore
        zip=comp.get("zip"),  # type: ignore
        city=comp.get("city"),  # type: ignore
        state=comp.get("state"),  # type: ignore
        country=comp.get("country"),  # type: ignore
        pg_geography=geography._point_to_database(  # type: ignore
            geopydantic.Point(
                type="Point",
                coordinates=(comp["longitude"], comp["latitude"]),  # type: ignore
            )
        ),
    )

    db.add(minigrid)
    db.commit()

    return True
