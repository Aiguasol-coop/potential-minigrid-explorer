import fastapi

import app._version


router = fastapi.APIRouter()


@router.get("/")
async def root():
    return {"message": "Hello from the PROJECTNAME API service!"}


@router.get("/version")
async def version():
    return {"version": f"{app._version.__version__}"}
