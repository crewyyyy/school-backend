from fastapi import APIRouter

from app.api import auth, classes, devices, events, system

api_router = APIRouter()
api_router.include_router(system.router)
api_router.include_router(auth.router)
api_router.include_router(classes.router)
api_router.include_router(events.router)
api_router.include_router(devices.router)

