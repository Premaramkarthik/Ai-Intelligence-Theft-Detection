from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from time import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.core.config import Settings, get_settings
from src.core.db import Database
from src.core.exceptions.handler import register_exception_handlers
from src.core.logger.logger import configure_logging
from src.routes.camera_routes import router as camera_router
from src.routes.health_routes import router as health_router
from src.routes.stream_routes import router as stream_router
from src.services.camera.camera_repository import CameraRepository
from src.services.camera.camera_service import CameraService
from src.services.camera.camera_validator import CameraValidator
from src.services.presentation.stream_contract_service import StreamContractService
from src.services.presentation.websocket_manager import WebSocketManager
from src.services.stream.kafka_event_consumer import StreamEventConsumer
from src.services.stream.stream_manager import StreamManager
from src.services.stream.stream_repository import StreamRepository
from src.services.stream.stream_service import StreamService


@dataclass(slots=True)
class ApplicationContainer:
    settings: Settings
    database: Database
    camera_service: CameraService
    stream_service: StreamService
    stream_manager: StreamManager
    websocket_manager: WebSocketManager
    kafka_consumer: StreamEventConsumer
    started_at_epoch: float


def create_application() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, settings.json_logs)
    settings.media_root.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database = Database(settings)
        await database.connect()

        camera_repository = CameraRepository(database)
        stream_repository = StreamRepository(database)
        camera_validator = CameraValidator(settings)
        camera_service = CameraService(camera_repository, camera_validator)
        stream_manager = StreamManager(settings)
        await stream_manager.start()
        websocket_manager = WebSocketManager()
        stream_contract_service = StreamContractService(settings)
        stream_service = StreamService(
            settings,
            camera_service,
            stream_repository,
            stream_manager,
            stream_contract_service,
        )
        kafka_consumer = StreamEventConsumer(settings, stream_service, websocket_manager)
        await kafka_consumer.start()

        app.state.container = ApplicationContainer(
            settings=settings,
            database=database,
            camera_service=camera_service,
            stream_service=stream_service,
            stream_manager=stream_manager,
            websocket_manager=websocket_manager,
            kafka_consumer=kafka_consumer,
            started_at_epoch=time(),
        )
        try:
            yield
        finally:
            await kafka_consumer.stop()
            await stream_manager.stop()
            await database.disconnect()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
        openapi_tags=[
            {"name": "Cameras", "description": "Camera CRUD and RTSP validation endpoints."},
            {"name": "Streams", "description": "Worker and playback contract endpoints."},
            {"name": "Health", "description": "Service, database, and stream health endpoints."},
        ],
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )
    register_exception_handlers(app)
    app.include_router(camera_router)
    app.include_router(stream_router)
    app.include_router(health_router)
    app.mount(
        settings.media_mount_path,
        StaticFiles(directory=str(settings.media_root)),
        name="media",
    )
    return app


app = create_application()
