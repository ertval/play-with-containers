import os
import json
import time
import logging
import signal
import threading
import pika
from app.orders import Order
from app.validation import InvalidOrderError, coerce_order_payload

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
    *undefined* variable as an empty string, which would defeat the default.
    """
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip()


def _env_port(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw.strip())
    except ValueError:
        logger.warning(f"Invalid value for {name}={raw!r}; falling back to {default}.")
        return default


def start_consuming(db_session_factory, stop_event=None):
    """Consume billing orders from RabbitMQ until `stop_event` is set.

    The consumer runs as PID 1's worker thread. On SIGTERM the process must stop
    cleanly: leaving `stop_event` unset means the loop never terminates, Docker
    waits out its 10 s grace period and SIGKILLs the container (exit 137).
    """
    if stop_event is None:
        stop_event = threading.Event()
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda *_: (
                logger.info("Shutdown signal received; stopping queue consumer"),
                stop_event.set(),
            ))

    # Non-secrets keep safe defaults; secrets MUST come from env.
    rabbitmq_host = _env_or_default("RABBITMQ_HOST", "rabbit-queue")
    rabbitmq_port = _env_port("RABBITMQ_PORT", 5672)
    rabbitmq_user = _require_env("RABBITMQ_USER")
    rabbitmq_password = _require_env("RABBITMQ_PASSWORD")
    queue_name = _env_or_default("RABBITMQ_QUEUE", "billing_queue")

    credentials = pika.PlainCredentials(rabbitmq_user, rabbitmq_password)
    parameters = pika.ConnectionParameters(
        host=rabbitmq_host,
        port=rabbitmq_port,
        credentials=credentials,
        heartbeat=60,
        blocked_connection_timeout=300
    )

    logger.info(f"Billing consumer starting up. Target queue: {queue_name} on {rabbitmq_host}:{rabbitmq_port}")

    while not stop_event.is_set():
        connection = None
        try:
            logger.info("Attempting connection to RabbitMQ broker...")
            connection = pika.BlockingConnection(parameters)
            channel = connection.channel()

            # Ensure the queue is durable
            channel.queue_declare(queue=queue_name, durable=True)
            channel.basic_qos(prefetch_count=1)

            logger.info(f"Connected to RabbitMQ. Waiting for billing messages on '{queue_name}'...")

            def callback(ch, method, properties, body):
                logger.info(f"Received raw message delivery #{method.delivery_tag}: {body.decode('utf-8', errors='replace')}")
                try:
                    payload = json.loads(body.decode("utf-8"))
                except Exception as json_err:
                    logger.error(f"Malformed non-JSON payload received: {json_err}. Acknowledging to avoid queue head-of-line blocking.")
                    ch.basic_ack(delivery_tag=method.delivery_tag)
                    return

                # Robust type coercion according to contract
                try:
                    user_id, number_of_items, total_amount = coerce_order_payload(payload)
                except InvalidOrderError as parse_err:
                    logger.error(f"Invalid order fields in payload {payload}: {parse_err}. Acknowledging and discarding poison message.")
                    ch.basic_ack(delivery_tag=method.delivery_tag)
                    return

                # Persist order to billing database with bounded retries
                db_success = False
                for retry in range(5):
                    if stop_event.is_set():
                        logger.info("Shutdown requested mid-retry; nacking message for redelivery")
                        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
                        return
                    session = db_session_factory()
                    try:
                        order = Order(
                            user_id=user_id,
                            number_of_items=number_of_items,
                            total_amount=total_amount
                        )
                        session.add(order)
                        session.commit()
                        logger.info(f"Successfully processed and recorded order #{order.id} for user '{user_id}' (items={number_of_items}, total=${total_amount:.2f})")
                        db_success = True
                        break
                    except Exception as db_err:
                        session.rollback()
                        logger.warning(f"Database insertion retry {retry + 1}/5 failed: {db_err}")
                        time.sleep(1)
                    finally:
                        session.close()

                if db_success:
                    # Acknowledge only after the transaction is committed, so a crash
                    # before this point causes RabbitMQ to redeliver the order.
                    ch.basic_ack(delivery_tag=method.delivery_tag)
                else:
                    # Never ack a failed insert: that would silently discard a
                    # customer order. Requeue so another worker (or a later
                    # delivery of this same message) can process it.
                    logger.error(f"Failed to persist order after retries; requeueing. Payload: {payload}")
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

            channel.basic_consume(queue=queue_name, on_message_callback=callback, auto_ack=False)

            # `start_consuming()` blocks this thread in the AMQP socket read and
            # never checks stop_event, so a shutdown request would otherwise be
            # ignored until the next message arrived. A watcher thread closes
            # the loop through pika's thread-safe callback mechanism.
            def _stop_on_shutdown():
                stop_event.wait()
                try:
                    connection.add_callback_threadsafe(channel.stop_consuming)
                except Exception as e:
                    logger.debug(f"Could not schedule stop_consuming: {e}")

            threading.Thread(
                target=_stop_on_shutdown,
                daemon=True,
                name="BillingQueueShutdownWatcher"
            ).start()

            channel.start_consuming()

        except (pika.exceptions.AMQPConnectionError, pika.exceptions.AMQPChannelError) as amqp_err:
            if stop_event.is_set():
                break
            logger.warning(f"RabbitMQ connection lost/unavailable: {amqp_err}. Retrying in 3 seconds...")
            time.sleep(3)
        except Exception as e:
            if stop_event.is_set():
                break
            logger.error(f"Unexpected error in consumer loop: {e}. Retrying in 3 seconds...")
            time.sleep(3)
        finally:
            if connection and connection.is_open:
                try:
                    connection.close()
                except Exception:
                    pass

    logger.info("Billing queue consumer stopped cleanly.")