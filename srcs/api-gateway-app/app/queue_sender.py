import os
import time
import logging
import pika

logger = logging.getLogger(__name__)


def _require_env(name: str) -> str:
    """Return required secret env var or raise (no hardcoded fallback for secrets)."""
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Missing required secret environment variable: {name}. "
            "Set it via .env / compose environment (see .env.example)."
        )
    return value.strip()


def _env_or_default(name: str, default: str) -> str:
    """Non-secret setting with a safe default.

    `os.getenv(name, default)` is not enough: Docker Compose interpolates an
    *undefined* variable as an empty string rather than leaving it unset, so a
    missing or partial `.env` would yield `""` and defeat the default.
    """
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip()


def _env_port(name: str, default: int) -> int:
    """Non-secret port with a safe default, tolerant of empty/blank values."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw.strip())
    except ValueError:
        logger.warning(f"Invalid value for {name}={raw!r}; falling back to {default}.")
        return default


class RabbitMQSender:
    def __init__(self):
        # Non-secrets keep safe defaults; secrets MUST come from env.
        self.host = _env_or_default("RABBITMQ_HOST", "rabbit-queue")
        self.port = _env_port("RABBITMQ_PORT", 5672)
        self.user = _require_env("RABBITMQ_USER")
        self.password = _require_env("RABBITMQ_PASSWORD")
        self.queue = _env_or_default("RABBITMQ_QUEUE", "billing_queue")
        logger.info(
            f"RabbitMQ sender configured: {self.host}:{self.port} queue='{self.queue}' user='{self.user}'"
        )

    def _get_connection(self):
        credentials = pika.PlainCredentials(self.user, self.password)
        parameters = pika.ConnectionParameters(
            host=self.host,
            port=self.port,
            credentials=credentials,
            connection_attempts=3,
            retry_delay=1,
            socket_timeout=5
        )
        return pika.BlockingConnection(parameters)

    def publish_message(self, message: str, max_retries: int = 5, backoff: float = 1.0) -> bool:
        """Publish a durable, persistent message with publisher confirms.

        `channel.confirm_delivery()` turns AMQP acknowledgements into synchronous
        guarantees, so a returned `True` means "the broker accepted and persisted
        the message", not merely "the bytes reached a socket". `mandatory=True`
        plus a return callback makes an unroutable message a hard failure instead
        of a silently dropped one.
        """
        last_exception = None
        for attempt in range(1, max_retries + 1):
            connection = None
            try:
                connection = self._get_connection()
                channel = connection.channel()
                channel.confirm_delivery()
                channel.queue_declare(queue=self.queue, durable=True)
                returned = []

                def _on_returned(channel, method, properties, body):
                    returned.append(method.routing_key)

                channel.add_on_return_callback(_on_returned)
                channel.basic_publish(
                    exchange="",
                    routing_key=self.queue,
                    body=message.encode("utf-8"),
                    properties=pika.BasicProperties(
                        delivery_mode=pika.DeliveryMode.Persistent,
                        content_type="application/json"
                    ),
                    mandatory=True
                )
                if returned:
                    raise RuntimeError(
                        f"Message was returned as unroutable (routing_key={returned[0]!r})"
                    )
                logger.info(f"Published message to queue '{self.queue}' on attempt {attempt}: {message}")
                return True
            except Exception as e:
                last_exception = e
                logger.warning(f"RabbitMQ publish attempt {attempt}/{max_retries} failed: {e}")
                if attempt < max_retries:
                    time.sleep(backoff * attempt)
            finally:
                if connection is not None and connection.is_open:
                    try:
                        connection.close()
                    except Exception:
                        pass

        logger.error(f"Failed to publish message after {max_retries} attempts: {last_exception}")
        raise RuntimeError(f"Could not publish message to RabbitMQ: {last_exception}")