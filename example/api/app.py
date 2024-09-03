from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
)


button_clicks: dict[str, int] = {}


class Clicks(BaseModel):
    clicks: int


def get_button_clicks(host: str) -> Clicks:
    clicks = button_clicks.get(host, 0)

    return Clicks(clicks=clicks)


@app.get("/clicks")
async def index(request: Request) -> Clicks:
    if request.client is None:
        raise HTTPException(401)

    host, _ = request.client

    return get_button_clicks(host)


@app.post("/click")
async def click(request: Request) -> Clicks:
    if request.client is None:
        raise HTTPException(401)

    host, _ = request.client

    button_clicks.setdefault(host, 0)
    button_clicks[host] += 1

    return get_button_clicks(host)


@app.post("/reset")
async def reset(request: Request) -> Clicks:
    if request.client is None:
        raise HTTPException(401)

    host, _ = request.client

    if host in button_clicks:
        del button_clicks[host]

    return get_button_clicks(host)
