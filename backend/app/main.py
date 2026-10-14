"""HLRAI API, slice S1 (read the register). Contract: openapi/openapi.yaml."""
import os
import re

from fastapi import Depends, FastAPI, Path as PathParam
from fastapi.exceptions import RequestValidationError
from fastapi.responses import Response

from . import service
from .errors import ApiError, api_error_handler, validation_error_handler
from .register_store import RegisterStore

SHA = re.compile(r"^[0-9a-f]{64}$")


def get_store() -> RegisterStore:
    return RegisterStore(os.environ.get("HLRAI_ROOT"), os.environ.get("HLRAI_STATE"))


def current_user():
    """DEV STUB, not authentication. Real OIDC lands with slice S3 (spec 4.4, pressure test row 3)."""
    if os.environ.get("HLRAI_ENV", "dev") != "dev":
        raise ApiError(401, "unauthenticated", "Authentication required", "Dev identity is disabled outside HLRAI_ENV=dev")
    return {"id": "dev-user", "name": os.environ.get("HLRAI_DEV_USER", "Venky R"),
            "role": os.environ.get("HLRAI_DEV_ROLE", "approver")}


def create_app() -> FastAPI:
    app = FastAPI(title="HLRAI API", version="0.1.0", docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    r = "/api/v1"

    @app.get(f"{r}/me")
    def get_me(user=Depends(current_user)):
        return user

    @app.get(f"{r}/register")
    def get_register(store=Depends(get_store)):
        return service.summary(store)

    @app.get(f"{r}/obligations/{{oid}}")
    def get_obligation(oid: str, store=Depends(get_store)):
        return service.obligation_detail(store, oid)

    @app.get(f"{r}/controls/{{cid}}")
    def get_control(cid: str, store=Depends(get_store)):
        return service.control_detail(store, cid)

    @app.get(f"{r}/revisions")
    def list_revisions(store=Depends(get_store)):
        return store.revisions()

    @app.get(f"{r}/revisions/{{a}}/diff/{{b}}")
    def diff_revisions(a: str = PathParam(pattern=SHA.pattern), b: str = PathParam(pattern=SHA.pattern),
                       store=Depends(get_store)):
        return service.diff(store, a, b)

    @app.get(f"{r}/export/register.yaml")
    def export_register(store=Depends(get_store)):
        return Response(store.raw(), media_type="application/yaml")

    return app


app = create_app()
