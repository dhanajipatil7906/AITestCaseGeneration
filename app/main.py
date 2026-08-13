from pathlib import Path
from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app.api.auth import router as auth_router
from app.api.analysis import router as analysis_router
from app.api.dependencies import CurrentUser, get_current_user_optional


BASE_DIR = Path(__file__).resolve().parent


app = FastAPI(
    title="AI Test Agent",
    description="Enterprise AI Agent for Functional Test Case Generation",
    version="0.1.0",
)


# Static files
app.mount(
    "/static",
    StaticFiles(
        directory=BASE_DIR / "static"
    ),
    name="static",
)


# Jinja2 templates
templates = Jinja2Templates(
    directory=BASE_DIR / "templates"
)


# Authentication API
app.include_router(auth_router)
app.include_router(analysis_router)


@app.get(
    "/",
    response_class=HTMLResponse,
)
def login_page(request: Request):

    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "request": request
        },
    )


@app.get(
    "/dashboard",
    response_class=HTMLResponse,
)
def dashboard_page(
    request: Request,
    current_user: CurrentUser | None = Depends(get_current_user_optional),
):
    if current_user is None:
        return templates.TemplateResponse(
            request=request,
            name="unauthorized.html",
            status_code=401,
            context={
                "request": request,
            },
        )

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "request": request,
            "current_user": current_user,
        },
    )


@app.get("/health")
def health_check():

    return {
        "status": "healthy",
        "application": "AI Test Agent",
    }