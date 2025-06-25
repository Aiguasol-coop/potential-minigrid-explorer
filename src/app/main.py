"""This module is the entry point for the HTTP server.

It contains:

- The FastAPI object that stores pointers to the path operation (aka handler) functions and the
  metadata for generating OpenAPI documentation.

- The general OpenAPI documentation for the service.
"""

import collections.abc
import contextlib
from enum import Enum

import fastapi
import fastapi.middleware.cors

import app._version
import app.general.api as general
import app.explorations.api as explorations


api = fastapi.FastAPI(lifespan=lambda app: startup_and_shutdown(app))
"""FastAPI object that we use as the entrypoint for the API service.

This can be run using either the ``fastapi`` executable or the ``uvicorn`` executable.
"""


class Tags(Enum):
    general = "general"
    explorations = "explorations"
    projects = "projects"


api.include_router(general.router, prefix="", tags=[Tags.general])
api.include_router(explorations.router, prefix="/explorations", tags=[Tags.explorations])


####################################################################################################
### Metadata for OpenAPI documentation #############################################################
####################################################################################################


api.title = "Potential Minigrid Explorer API"
api.description = "Potential minigrid explorer, to be used in combination with the offgridplanner."
api.version = ".".join([str(app._version.version_tuple[0]), str(app._version.version_tuple[1])])


####################################################################################################
### API middlewares ################################################################################
####################################################################################################


api.add_middleware(
    fastapi.middleware.cors.CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@contextlib.asynccontextmanager
async def startup_and_shutdown(app: fastapi.FastAPI) -> collections.abc.AsyncGenerator[None]:
    """Prepare the context to run the HTTP server (read env. vars., start the DB engine, etc.), and
    then destroy it.

    :yield: It doesn't yield any value, but HTTP requests are handled here.
    """
    try:
        # Startup code goes here
        yield None
    finally:
        # Shutdown code goes here
        pass
