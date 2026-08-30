from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.db.database import init_db
from api.routes.main import router as main_router

API_PREFIX = "/api/v1"

app = FastAPI(title="codeduck", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()
app.include_router(main_router, prefix=API_PREFIX)
