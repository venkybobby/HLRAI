"""RFC 7807 problem responses. `code` values are fixed by openapi/openapi.yaml (Problem.code)."""
from fastapi import Request
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(self, status, code, title, detail=None, violations=None):
        self.status, self.code, self.title, self.detail, self.violations = status, code, title, detail, violations


def problem_body(status, code, title, detail=None, violations=None):
    body = {"type": f"about:blank#{code}", "title": title, "status": status, "code": code}
    if detail:
        body["detail"] = detail
    if violations:
        body["violations"] = violations
    return body


async def api_error_handler(_: Request, exc: ApiError):
    return JSONResponse(problem_body(exc.status, exc.code, exc.title, exc.detail, exc.violations),
                        status_code=exc.status, media_type="application/problem+json")


async def validation_error_handler(_: Request, exc):
    v = [f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()]
    return JSONResponse(problem_body(422, "schema_invalid", "Request validation failed", violations=v),
                        status_code=422, media_type="application/problem+json")
