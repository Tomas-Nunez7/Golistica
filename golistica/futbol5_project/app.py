from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from pathlib import Path

# Initialize FastAPI app
app = FastAPI()

# Mount static files
app.mount(
    "/static",
    StaticFiles(directory="static"),
    name="static"
)

# Setup templates
templates = Jinja2Templates(directory="templates")

# Main route
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# Include API routes
from backend import main as backend_main
app.include_router(backend_main.router, prefix="/api")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
