from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse, ORJSONResponse
from fastapi.staticfiles import StaticFiles

from app.apis.v1 import v1_routers
from app.core.db.databases import initialize_tortoise
from app.patient.service import PatientFlowError

app = FastAPI(
    default_response_class=ORJSONResponse, docs_url="/api/docs", redoc_url="/api/redoc", openapi_url="/api/openapi.json"
)
initialize_tortoise(app)

app.include_router(v1_routers)

patient_frontend = Path(__file__).resolve().parent.parent / "frontend" / "patient"
if patient_frontend.exists():
    app.mount("/patient", StaticFiles(directory=patient_frontend, html=True), name="patient")


@app.exception_handler(PatientFlowError)
async def patient_flow_error_handler(_, exc: PatientFlowError) -> JSONResponse:
    content: dict[str, object] = {"code": exc.code, "detail": exc.message}
    if exc.retry_after_seconds is not None:
        content["retry_after_seconds"] = exc.retry_after_seconds
    return JSONResponse(status_code=exc.status_code, content=content)
