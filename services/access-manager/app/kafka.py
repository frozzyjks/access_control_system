import asyncio
import logging
from typing import Protocol
from aiokafka import AIOKafkaProducer
from app.events import AccessRequestCreatedEvent
from app.schemas import AccessRequestRead


class AccessRequestEventPublisher(Protocol):

    async def publish_request_created(self, request: AccessRequestRead) -> None:
        """Publish event that a request has been created"""


class KafkaAccessRequestEventPublisher:

    def __init__(
        self,
        *,
        bootstrap_servers: str,
        topic: str,
        logger: logging.Logger,
    ) -> None:

        self._bootstrap_servers = bootstrap_servers
        self._topic = topic
        self._logger = logger
        self._producer: AIOKafkaProducer | None = None
        self._start_lock = asyncio.Lock()

    async def publish_request_created(self, request: AccessRequestRead) -> None:

        await self._ensure_started()

        event = AccessRequestCreatedEvent.from_request(request)
        key = str(event.request_id).encode("utf-8")
        value = event.model_dump_json().encode("utf-8")

        assert self._producer is not None

        self._logger.info(
            "Publishing access request event: request_id=%s topic=%s",
            event.request_id,
            self._topic,
        )

        await self._producer.send_and_wait(self._topic, value=value, key=key)

    async def close(self) -> None:

        if self._producer is None:
            return

        self._logger.info("Stopping Kafka producer")
        await self._producer.stop()
        self._producer = None

    async def _ensure_started(self) -> None:

        if self._producer is not None:
            return

        async with self._start_lock:
            if self._producer is not None:
                return

            self._logger.info(
                "Starting Kafka producer: bootstrap_servers=%s",
                self._bootstrap_servers,
            )
            self._producer = AIOKafkaProducer(
                bootstrap_servers=self._bootstrap_servers,
            )
            await self._producer.start()
