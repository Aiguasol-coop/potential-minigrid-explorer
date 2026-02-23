from __future__ import annotations

from dataclasses import dataclass
import enum
import uuid
import geoalchemy2
import sqlalchemy
import sqlmodel

import app.shared.geography as geography

# These match the SDS dashboard tiles ("Este día")
DASHBOARD_KPIS: dict[str, str] = {
    "CONSUMPTION": "consumption_kwh_day",
    "ENERGY GENERATION": "generation_kwh_day",
    "CHARGED ENERGY": "charged_kwh_day",
    "DISCHARGED ENERGY": "discharged_kwh_day",
    "SELF-CONSUMPTION": "self_consumption_kwh_day",
}


@dataclass
class SensorInfo:
    name: str
    uuid: str


class AlarmType(str, enum.Enum):
    NEW = "new"
    OPEN = "open"
    CLOSED = "closed"


class MonitoringMinigridBase(sqlmodel.SQLModel):
    uuid: str = sqlmodel.Field(index=True, unique=True)
    identifier: str | None = None
    provider: str | None = None
    name: str | None = None
    typology: str | None = None
    timezone: str | None = None
    address: str | None = None
    zip: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None


class MonitoringMinigrid(MonitoringMinigridBase, geography.HasPointColumn, table=True):
    __tablename__ = "monitoring_mini_grids"  # type: ignore

    id: str | None = sqlmodel.Field(
        default_factory=lambda: str(uuid.uuid4()), primary_key=True, index=True
    )

    pg_geography: str = sqlmodel.Field(
        default=None,
        sa_column=sqlalchemy.Column(
            geoalchemy2.Geography(geometry_type="POINT", srid=4326), nullable=False
        ),
    )
