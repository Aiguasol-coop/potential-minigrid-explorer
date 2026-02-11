import datetime

import sqlalchemy
import sqlmodel


class HouseholdData(sqlmodel.SQLModel, table=True):
    """Store household consumption data by subcategory for different area types."""

    id: int = sqlmodel.Field(primary_key=True, default=None)
    area_type: str  # 'periurban' or 'isolated'
    subcategory: str  # 'very_low', 'low', 'middle', 'high', 'very_high'
    kwh_per_day: float
    distribution: float
    created_at: datetime.datetime = sqlmodel.Field(default_factory=datetime.datetime.now)

    @property
    def as_dict(self) -> dict[str, float]:
        return {
            "kwh_per_day": self.kwh_per_day,
            "distribution": self.distribution,
        }


class EnterpriseData(sqlmodel.SQLModel, table=True):
    """Store enterprise consumption data by subcategory for different area types."""

    id: int = sqlmodel.Field(primary_key=True, default=None)
    area_type: str  # 'periurban' or 'isolated'
    subcategory: str  # Food_Groceries, Retail_Kiosk, etc.
    kwh_per_day: float
    distribution: float
    created_at: datetime.datetime = sqlmodel.Field(default_factory=datetime.datetime.now)

    @property
    def as_dict(self) -> dict[str, float]:
        return {
            "kwh_per_day": self.kwh_per_day,
            "distribution": self.distribution,
        }


class PublicServiceData(sqlmodel.SQLModel, table=True):
    """Store public service consumption data by subcategory for different area types."""

    id: int = sqlmodel.Field(primary_key=True, default=None)
    area_type: str  # 'periurban' or 'isolated'
    subcategory: str  # Health_Health Centre, Health_Clinic, etc.
    kwh_per_day: float
    distribution: float
    created_at: datetime.datetime = sqlmodel.Field(default_factory=datetime.datetime.now)

    @property
    def as_dict(self) -> dict[str, float]:
        return {
            "kwh_per_day": self.kwh_per_day,
            "distribution": self.distribution,
        }


class HouseholdHourlyProfile(sqlmodel.SQLModel, table=True):
    """Store household hourly consumption profiles."""

    id: int = sqlmodel.Field(primary_key=True, default=None)
    area_type: str  # 'periurban' or 'isolated'
    subcategory: str  # 'very_low', 'low', 'middle', 'high', 'very_high'
    hourly_profile: dict[str, float] = sqlmodel.Field(sa_column=sqlalchemy.Column(sqlalchemy.JSON))
    created_at: datetime.datetime = sqlmodel.Field(default_factory=datetime.datetime.now)


class EnterpriseHourlyProfile(sqlmodel.SQLModel, table=True):
    """Store enterprise hourly consumption profiles."""

    id: int = sqlmodel.Field(primary_key=True, default=None)
    subcategory: str  # Food_Groceries, Retail_Kiosk, etc.
    hourly_profile: dict[str, float] = sqlmodel.Field(sa_column=sqlalchemy.Column(sqlalchemy.JSON))
    created_at: datetime.datetime = sqlmodel.Field(default_factory=datetime.datetime.now)


class PublicServiceHourlyProfile(sqlmodel.SQLModel, table=True):
    """Store public service hourly consumption profiles."""

    id: int = sqlmodel.Field(primary_key=True, default=None)
    subcategory: str  # Health_Health Centre, Health_Clinic, etc.
    hourly_profile: dict[str, float] = sqlmodel.Field(sa_column=sqlalchemy.Column(sqlalchemy.JSON))
    created_at: datetime.datetime = sqlmodel.Field(default_factory=datetime.datetime.now)
