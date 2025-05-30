import asyncio
import aio_pika
import json
import logging
from typing import Optional

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RabbitMQConsumer:
    def __init__(self):
        self.connection: Optional[aio_pika.RobustConnection] = None
        self.channel: Optional[aio_pika.RobustChannel] = None
        self.queue: Optional[aio_pika.RobustQueue] = None

    async def connect(self, retry_interval: int = 5, max_retries: int = 10) -> None:
        """Установка соединения с RabbitMQ с автоматическими повторами"""
        for attempt in range(1, max_retries + 1):
            try:
                self.connection = await aio_pika.connect_robust(
                    "amqp://guest:guest@rabbitmq/",
                    timeout=5
                )
                self.channel = await self.connection.channel()
                await self.channel.set_qos(prefetch_count=10)
                self.queue = await self.channel.declare_queue(
                    "events",
                    durable=True,
                    arguments={
                        "x-message-ttl": 86400000,  # 24 часа в ms
                        "x-queue-mode": "lazy"  # Сохранение на диск
                    }
                )
                logger.info("Successfully connected to RabbitMQ")
                return
            except Exception as e:
                logger.warning(f"Connection attempt {attempt}/{max_retries} failed: {str(e)}")
                if attempt < max_retries:
                    await asyncio.sleep(retry_interval)

        raise ConnectionError("Failed to connect to RabbitMQ")

    async def process_message(self, message: aio_pika.IncomingMessage) -> None:
        """Обработка входящих сообщений"""
        async with message.process():
            try:
                body = json.loads(message.body.decode())
                logger.info(f"Received message: {body}")
                # Здесь бизнес-логика обработки
            except json.JSONDecodeError:
                logger.error("Invalid JSON format")
            except Exception as e:
                logger.error(f"Processing error: {str(e)}")
                await message.nack()  # Возврат в очередь при ошибке

    async def consume(self) -> None:
        """Основной цикл потребления сообщений"""
        await self.connect()

        try:
            logger.info("Starting message consumption...")
            await self.queue.consume(self.process_message)

            # Бесконечное ожидание (можно заменить на asyncio.Event)
            while True:
                await asyncio.sleep(1)
                if self.connection.is_closed:
                    raise ConnectionError("Connection lost")

        except Exception as e:
            logger.error(f"Consumer error: {str(e)}")
            await self.reconnect()

    async def reconnect(self) -> None:
        """Переподключение при разрыве соединения"""
        if self.connection:
            await self.connection.close()

        logger.info("Attempting to reconnect...")
        await asyncio.sleep(5)
        await self.consume()


async def main():
    consumer = RabbitMQConsumer()
    await consumer.consume()


if __name__ == "__main__":
    asyncio.run(main())