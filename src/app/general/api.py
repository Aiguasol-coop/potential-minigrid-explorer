import enum

import fastapi
import sqlmodel

import app._version
import app.db.core as db
from app.explorations.domain import (
    PublicServiceData,
    HouseholdData,
    EnterpriseData,
    HouseholdHourlyProfile,
)

router = fastapi.APIRouter()

####################################################################################################
###   MODELS AND DB ENTITIES   #####################################################################
####################################################################################################


class HouseHoldDataResponse(sqlmodel.SQLModel):
    subcategory: str
    kwh_per_day: float
    distribution: float


class HouseHoldProfileResponse(sqlmodel.SQLModel):
    subcategory: str
    hourly_profile: dict[str, float]


class AreaType(enum.Enum):
    isolated = "isolated"
    periurban = "periurban"


####################################################################################################
###   FASTAPI PATH OPERATIONS   ####################################################################
####################################################################################################


@router.get("/")
async def root():
    return {"message": "Hello from the potential-minigrid-explorer API service!"}


@router.get("/version")
async def version():
    return {"version": f"{app._version.__version__}"}


@router.get("/enterprise_categories")
def enterprise_categories(db: db.Session) -> list[str]:
    categories: list[str] = list(
        db.exec(
            sqlmodel.select(EnterpriseData.subcategory)
            .distinct()
            .order_by(EnterpriseData.subcategory)
        ).all()
    )

    return categories


@router.get("/public_service_categories")
def public_service_categories(db: db.Session) -> list[str]:
    categories: list[str] = list(
        db.exec(
            sqlmodel.select(PublicServiceData.subcategory)
            .distinct()
            .order_by(PublicServiceData.subcategory)
        ).all()
    )

    return categories


@router.get("/household_categories")
def household_categories(db: db.Session, area_type: AreaType) -> list[HouseHoldDataResponse]:
    categories: list[HouseholdData] = list(
        db.exec(sqlmodel.select(HouseholdData).where(HouseholdData.area_type == area_type)).all()
    )

    return [HouseHoldDataResponse.model_validate(cat) for cat in categories]


@router.get("/household_profiles")
def household_profiles(db: db.Session, area_type: AreaType) -> list[HouseHoldProfileResponse]:
    profiles: list[HouseholdHourlyProfile] = list(
        db.exec(
            sqlmodel.select(HouseholdHourlyProfile).where(
                HouseholdHourlyProfile.area_type == area_type
            )
        ).all()
    )

    return [HouseHoldProfileResponse.model_validate(profile) for profile in profiles]
