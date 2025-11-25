from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
import os
from pathlib import Path

app = FastAPI()

# Obtener la ruta absoluta al directorio actual
BASE_DIR = Path(__file__).resolve().parent

# Configurar archivos estáticos
app.mount(
    "/static",
    StaticFiles(directory=str(BASE_DIR / "static")),
    name="static"
)

# Configurar plantillas
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Ruta principal
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("simple_app:app", host="0.0.0.0", port=8000, reload=False)
