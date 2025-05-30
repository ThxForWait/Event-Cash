from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
import json
import aio_pika
import redis.asyncio as redis
from pydantic import BaseModel
from datetime import datetime

app = FastAPI()

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # можно заменить на ["http://localhost:3000"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

r = redis.Redis(host="redis", port=6379, decode_responses=True)


async def send_event_rabbit(message):
    connection = await aio_pika.connect_robust("amqp://guest:guest@rabbitmq/")
    channel = await connection.channel()
    queue = await channel.get_queue("events")

    event = {
        "message": f"{message}",
        "timestamp": datetime.now().isoformat()
    }
    await channel.default_exchange.publish(
        aio_pika.Message(
             body=json.dumps(event).encode()
        ),
        routing_key="events"
    )
    #print("message :" + f"{message}")



class KeyRequest(BaseModel):
    key: str

@app.post("/add")
async def add_key(request: KeyRequest):
    try:
        exists = await r.exists(request.key)
        ##old_ttl = await r.ttl(request.key)
        # Добавляем запись с TTL 60 секунд
        ##r.setex(request.key, 60, "active")
        if exists:
            current_ttl = await r.ttl(request.key)
            #print(f"Запись есть! Старый TTL: {current_ttl} сек.")
            ##r.expire(request.key, 60)  # Обновляем TTL до 60 сек
            await send_event_rabbit(f"Ключ '{request.key}' существует (TTL: {current_ttl} сек)")
            return JSONResponse(
                content={"status": "success", "message": f"Ключ '{request.key}' существует (TTL: {current_ttl} сек)"},
                status_code=200
            )
        else:
            #print("Записи нет, создаем новую с TTL 60 сек.")
            await r.set(request.key, "active", ex=60)
            await send_event_rabbit(f"Ключ '{request.key}' добавлен (TTL: 60 сек)")
            return JSONResponse(
                content={"status": "success", "message": f"Ключ '{request.key}' добавлен (TTL: 60 сек)"},
                status_code=200
            )
    except Exception as e:
        return JSONResponse(
            content={"status": "error", "message": str(e)},
            status_code=500
        )

@app.post("/delete")
async def delete_key(request: KeyRequest):
    try:
        exists = await r.exists(request.key)
        #print("запись удалена")
        if exists:
            await r.delete(request.key)
            await send_event_rabbit(f"Ключ '{request.key}' удален")
            return JSONResponse(
                content={"status": "success", "message": f"Ключ '{request.key}' удален"},
                status_code=200
            )
        else:
            await send_event_rabbit(f"Ключ '{request.key}' не найден")
            return JSONResponse(
                content={"status": "success", "message": f"Ключ '{request.key}' не найден"},
                status_code=404
            )
    except Exception as e:
        return JSONResponse(
            content={"status": "error", "message": str(e)},
            status_code=500
        )




