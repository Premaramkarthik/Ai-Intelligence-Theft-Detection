from __future__ import annotations

from types import SimpleNamespace

import pytest
from aiokafka.errors import KafkaConnectionError
from src.core.config import Settings
from src.services.presentation.websocket_manager import WebSocketManager
from src.services.stream.kafka_event_consumer import StreamEventConsumer


class FailingConsumer:
    def __init__(self, *_args, **_kwargs) -> None:
        self.stop_called = False

    async def start(self) -> None:
        raise KafkaConnectionError("boom")

    async def stop(self) -> None:
        self.stop_called = True


@pytest.mark.asyncio
async def test_kafka_consumer_start_cleans_up_failed_consumer(monkeypatch) -> None:
    created: list[FailingConsumer] = []

    def build_consumer(*args, **kwargs) -> FailingConsumer:
        consumer = FailingConsumer(*args, **kwargs)
        created.append(consumer)
        return consumer

    monkeypatch.setattr(
        "src.services.stream.kafka_event_consumer.AIOKafkaConsumer",
        build_consumer,
    )

    settings = Settings(
        database_url="postgresql://postgres:postgres@localhost:5432/test_db",
        kafka_enabled=True,
        _env_file=None,
    )
    consumer = StreamEventConsumer(
        settings,
        stream_service=SimpleNamespace(),
        websocket_manager=WebSocketManager(),
    )

    await consumer.start()

    assert len(created) == 1
    assert created[0].stop_called is True
    assert consumer.health_snapshot()["healthy"] is False
    assert consumer.health_snapshot()["last_error"] == "KafkaConnectionError: boom"
