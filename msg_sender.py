from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request
from starlette.templating import Jinja2Templates
from typing import List

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

# Lista websockets conectados
connected_websockets: List[WebSocket] = []

@app.get("/", response_class=HTMLResponse)
async def read_index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await websocket.accept()
    connected_websockets.append(websocket)

    try:
        # Notificar a los clientes conectados que un nuevo usuario se ha unido
        await notify_users(f"User {client_id} connected", exclude_websocket=websocket)

        while True:
            data = await websocket.receive_text()
            await broadcast_message(data, sender=client_id)
    except WebSocketDisconnect:
        connected_websockets.remove(websocket)
        # Notificar a los clientes conectados que un usuario se ha desconectado
        await notify_users(f"User {client_id} disconnected")

async def notify_users(message: str, exclude_websocket: WebSocket = None):
    for ws in connected_websockets:
        if ws != exclude_websocket:
            await ws.send_text(message)

async def broadcast_message(message: str, sender: str):
    for ws in connected_websockets:
        if ws != sender:
            await ws.send_text(message)

