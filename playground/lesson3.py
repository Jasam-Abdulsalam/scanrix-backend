import asyncio
import time
from fastapi import FastAPI

app = FastAPI()

@app.get("/fast")
async def fast():
    return {"ok": True}

@app.get("/slow-blocking")
async def slow_blocking():
    time.sleep(5)                 # blocking call inside async def
    return {"done": "blocking"}

@app.get("/slow-async")
async def slow_async():
    await asyncio.sleep(5)        # non-blocking wait
    return {"done": "async"}

@app.get("/slow-def")
def slow_def():
    time.sleep(5)                 # blocking, but in a plain def
    return {"done": "def"}