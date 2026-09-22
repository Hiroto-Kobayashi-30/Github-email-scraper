from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router
from api.ws import router as ws_router
from core.config import settings

app = FastAPI(title="GitHub Email Scraper", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://github-email-scraper-hiroto.vercel.app",
        "http://localhost:3000",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(ws_router)


@app.get("/")
async def root():
    return {"name": "GitHub Email Scraper", "status": "online"}
