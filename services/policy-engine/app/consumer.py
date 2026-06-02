import asyncio
import json
import logging
from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaError
from pydantic import ValidationError
from app.clients import ResourceCatalogClient, ResourceCatalogClientError
from app.schemas import AccessRequestEvent, RequestStatus
from app.validator import AccessRequestValidator, ValidationResult, build_decision

_HANDLED_EVENT_TYPE = "ACCESS_REQUEST_CREATED"


class AccessRequestConsumer:

    def __init__(
        self,
        *,
        bootstrap_servers: str,
        topic: str,
        group_id: str,
        resource_catalog_client: ResourceCatalogClient,
        logger: logging.Logger,
    ) -> None:

        self._bootstrap_servers = bootstrap_servers
        self._topic = topic
        self._group_id = group_id
        self._resource_catalog_client = resource_catalog_client
        self._logger = logger
        self._consumer: AIOKafkaConsumer | None = None
        self._task: asyncio.Task | None = None

    async def start(self) -> None:

        self._logger.info(
            "Starting Kafka consumer: topic=%s group_id=%s",
            self._topic,
            self._group_id,
        )

        self._consumer = AIOKafkaConsumer(
            self._topic,
            bootstrap_servers=self._bootstrap_servers,
            group_id=self._group_id,
            auto_offset_reset="earliest",
            enable_auto_commit=True,
            auto_commit_interval_ms=1000,
            value_deserializer=lambda v: v.decode("utf-8"),
            key_deserializer=lambda k: k.decode("utf-8") if k else None,
        )

        await self._consumer.start()
        self._logger.info("Kafka consumer started successfully")

        self._task = asyncio.create_task(
            self._consume_loop(),
            name="kafka-consumer-loop",
        )

    async def stop(self) -> None:

        self._logger.info("Stopping Kafka consumer")

        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        if self._consumer is not None:
            await self._consumer.stop()
            self._logger.info("Kafka consumer stopped")

    async def _consume_loop(self) -> None:

        self._logger.info("Kafka consume loop started")
        assert self._consumer is not None

        try:
            async for message in self._consumer:
                await self._handle_message(message)
        except asyncio.CancelledError:
            self._logger.info("Kafka consume loop cancelled")
            raise
        except KafkaError as exc:
            self._logger.error("Kafka error in consume loop: %s", exc)
        except Exception as exc:
            self._logger.exception("Unexpected error in consume loop: %s", exc)

    async def _handle_message(self, message: object) -> None:

        topic = getattr(message, "topic", "unknown")
        partition = getattr(message, "partition", -1)
        offset = getattr(message, "offset", -1)
        value = getattr(message, "value", "")

        self._logger.debug(
            "Received message: topic=%s partition=%s offset=%s",
            topic,
            partition,
            offset,
        )

        event = self._parse_event(value)
        if event is None:
            return

        if event.event_type != _HANDLED_EVENT_TYPE:
            self._logger.debug(
                "Skipping unknown event type: %s",
                event.event_type,
            )
            return

        await self._process_event(event)

    def _parse_event(self, raw_value: str) -> AccessRequestEvent | None:

        try:
            data = json.loads(raw_value)
        except json.JSONDecodeError as exc:
            self._logger.error(
                "Failed to parse Kafka message as JSON: %s | raw=%s",
                exc,
                raw_value[:200],
            )
            return None

        try:
            return AccessRequestEvent.model_validate(data)
        except ValidationError as exc:
            self._logger.error(
                "Kafka message does not match AccessRequestEvent schema: %s",
                exc,
            )
            return None

    async def _process_event(self, event: AccessRequestEvent) -> None:

        self._logger.info(
            "Processing event: request_id=%s user=%s operation=%s target_type=%s",
            event.request_id,
            event.user_id,
            event.operation,
            event.target_type,
        )

        validator = AccessRequestValidator(
            resource_catalog_client=self._resource_catalog_client,
            logger=self._logger,
        )

        try:
            result, request_was_found = await self._validate_safely(
                validator,
                event,
            )
        except ResourceCatalogClientError as exc:
            self._logger.error(
                "Resource Catalog error during validation: "
                "request_id=%s error=%s",
                event.request_id,
                exc,
            )
            return
        except Exception as exc:
            self._logger.exception(
                "Unexpected error during validation: request_id=%s error=%s",
                event.request_id,
                exc,
            )
            return

        if not request_was_found:
            return

        await self._send_decision_safely(event, result)

    async def _validate_safely(
        self,
        validator: AccessRequestValidator,
        event: AccessRequestEvent,
    ) -> tuple[ValidationResult, bool]:

        try:
            request = await self._resource_catalog_client.get_access_request(
                event.request_id,
            )
        except ResourceCatalogClientError as exc:
            if exc.status_code == 404:
                self._logger.warning(
                    "Request not found before validation, skipping: "
                    "request_id=%s",
                    event.request_id,
                )
                return ValidationResult.approve(), False
            raise

        from app.schemas import RequestStatus
        if request.status != RequestStatus.PENDING:
            self._logger.info(
                "Request not PENDING before validation, skipping: "
                "request_id=%s status=%s",
                event.request_id,
                request.status,
            )
            return ValidationResult.approve(), False

        result = await validator.validate(event.request_id)
        return result, True

    async def _send_decision_safely(
        self,
        event: AccessRequestEvent,
        result: ValidationResult,
    ) -> None:

        decision = build_decision(result)

        self._logger.info(
            "Sending decision: request_id=%s status=%s rejection_reason=%s",
            event.request_id,
            decision.status,
            decision.rejection_reason,
        )

        try:
            await self._resource_catalog_client.apply_decision(
                event.request_id,
                decision,
            )
        except ResourceCatalogClientError as exc:
            if exc.status_code == 400:
                self._logger.info(
                    "Request already processed (duplicate delivery): "
                    "request_id=%s",
                    event.request_id,
                )
                return

            self._logger.error(
                "Failed to send decision to Resource Catalog: "
                "request_id=%s error=%s",
                event.request_id,
                exc,
            )