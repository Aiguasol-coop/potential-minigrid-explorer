import enum
import pydantic


class ErrorResponse(pydantic.BaseModel):
    detail: str


class OkResponse(pydantic.BaseModel):
    ok: bool
    message: str | None = None


class CustomError(Exception):
    def __init__(self, message: str):
        super().__init__(message)


class BadRequestDepsPreventDeletion(str, enum.Enum):
    dependencies_prevent_deletion = (
        "The object you try to delete depends on other object that cannot be deleted on cascade"
    )
