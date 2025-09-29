import enum
from collections.abc import Sequence

import fastapi
import sqlmodel

import app.db.core as db
from app.profiles.domain import (
    EnterpriseData,
    EnterpriseHourlyProfile,
    HouseholdData,
    HouseholdHourlyProfile,
    PublicServiceData,
    PublicServiceHourlyProfile,
)

####################################################################################################
###   MODELS AND DB ENTITIES   #####################################################################
####################################################################################################


class AreaType(str, enum.Enum):
    isolated = "isolated"
    periurban = "periurban"


class ProfileResponse(sqlmodel.SQLModel):
    area_type: AreaType | None
    subcategory: str
    distribution: float
    kwh_per_day: float
    hourly_profile: dict[str, float]


####################################################################################################
###   FASTAPI PATH OPERATIONS   ####################################################################
####################################################################################################


router = fastapi.APIRouter()


@router.get("/enterprise")
def enterprise_profiles(
    db: db.Session,
    area_type: AreaType | None = fastapi.Query(default=None),
    subcategory: str | None = fastapi.Query(default=None),
) -> Sequence[ProfileResponse]:
    profiles = db.exec(
        sqlmodel.select(EnterpriseHourlyProfile, EnterpriseData).where(
            sqlmodel.or_(
                EnterpriseData.area_type == area_type, True if area_type is None else False
            ),
            sqlmodel.or_(
                EnterpriseData.subcategory == subcategory,
                True if subcategory is None else False,
            ),
            # No area_type available for EnterpriseHourlyProfile
            EnterpriseData.subcategory == EnterpriseHourlyProfile.subcategory,
        )
    ).all()

    return [
        ProfileResponse.model_validate(hourly, update=data.model_dump())
        for hourly, data in profiles
    ]


@router.get("/enterprise/subcategories")
def enterprise_subcategories(db: db.Session) -> Sequence[str]:
    categories = db.exec(
        sqlmodel.select(EnterpriseData.subcategory).distinct().order_by(EnterpriseData.subcategory)
    ).all()

    return categories


@router.get("/household")
def household_profiles(
    db: db.Session,
    area_type: AreaType | None = fastapi.Query(default=None),
    subcategory: str | None = fastapi.Query(default=None),
) -> Sequence[ProfileResponse]:
    profiles = db.exec(
        sqlmodel.select(HouseholdHourlyProfile, HouseholdData).where(
            sqlmodel.or_(
                HouseholdData.area_type == area_type, True if area_type is None else False
            ),
            sqlmodel.or_(
                HouseholdData.subcategory == subcategory,
                True if subcategory is None else False,
            ),
            HouseholdData.area_type == HouseholdHourlyProfile.area_type,
            HouseholdData.subcategory == HouseholdHourlyProfile.subcategory,
        )
    ).all()

    return [
        ProfileResponse.model_validate(hourly, update=data.model_dump())
        for hourly, data in profiles
    ]


@router.get("/household/subcategories")
def household_subcategories(db: db.Session) -> Sequence[str]:
    categories = db.exec(
        sqlmodel.select(HouseholdData.subcategory).distinct().order_by(HouseholdData.subcategory)
    ).all()

    return categories


@router.get("/public_service")
def public_service_profiles(
    db: db.Session,
    area_type: AreaType | None = fastapi.Query(default=None),
    subcategory: str | None = fastapi.Query(default=None),
) -> Sequence[ProfileResponse]:
    profiles = db.exec(
        sqlmodel.select(PublicServiceHourlyProfile, PublicServiceData).where(
            sqlmodel.or_(
                PublicServiceData.area_type == area_type, True if area_type is None else False
            ),
            sqlmodel.or_(
                PublicServiceData.subcategory == subcategory,
                True if subcategory is None else False,
            ),
            # No area_type available for PublicServiceHourlyProfile
            PublicServiceData.subcategory == PublicServiceHourlyProfile.subcategory,
        )
    ).all()

    return [
        ProfileResponse.model_validate(hourly, update=data.model_dump())
        for hourly, data in profiles
    ]


@router.get("/public_service/subcategories")
def public_service_subcategories(db: db.Session) -> Sequence[str]:
    categories = db.exec(
        sqlmodel.select(PublicServiceData.subcategory)
        .distinct()
        .order_by(PublicServiceData.subcategory)
    ).all()

    return categories
