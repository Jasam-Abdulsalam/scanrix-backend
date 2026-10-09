from fastapi import FastAPI

app = FastAPI()

@app.get("/ping")
def ping():
    return {"pong": True}

@app.get("/items/{item_id}")
def get_item(item_id: int, verbose: bool = False):
    return {"item_id": item_id, "verbose": verbose}