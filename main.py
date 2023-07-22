from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from starlette.requests import Request
from starlette.templating import Jinja2Templates
import json
import random
import string
from aiortc import RTCConfiguration, RTCIceServer, RTCPeerConnection

app = FastAPI()
templates = Jinja2Templates(directory="templates")
connected_peers = {}
active_clients = set()

# Definimos Stun
stun_server = RTCIceServer(urls="stun:stun.l.google.com:19302")

configuration = RTCConfiguration(iceServers=[stun_server])

class WebSocketRTC:
    def __init__(self, websocket: WebSocket, configuration: RTCConfiguration):
        self.websocket = websocket
        self.configuration = configuration

    async def on_connect(self, client_id: str):
        await self.websocket.accept()
        peer = RTCPeerConnection(configuration=self.configuration)
        connected_peers[client_id] = {"peer": peer, "websocket": self.websocket}
        active_clients.add(client_id)

    async def on_receive(self, data: str):
        message = json.loads(data)
        sender_id = message.get("sender_id")
        recipient_id = message.get("recipient_id")

        if recipient_id in connected_peers:
            recipient_connection = connected_peers[recipient_id]["websocket"]
            await recipient_connection.send_text(data)

    async def on_disconnect(self, close_code: int):
        client_id = None
        for key, value in connected_peers.items():
            if value["websocket"] == self.websocket:
                client_id = key
                break

        if client_id:
            del connected_peers[client_id]
            active_clients.discard(client_id)


@app.get("/", response_class=HTMLResponse)
async def read_index(request: Request):
    client_id = generate_unique_client_id()
    return templates.TemplateResponse("main.html", {"request": request, "client_id": client_id})

@app.get("/available-clients")
async def get_available_clients():
    return list(active_clients)

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    rtc_websocket = WebSocketRTC(websocket, configuration)
    await rtc_websocket.on_connect(client_id)

    try:
        while True:
            data = await websocket.receive_text()
            await rtc_websocket.on_receive(data)
    except WebSocketDisconnect:
        await rtc_websocket.on_disconnect()
        active_clients.discard(client_id)

def generate_unique_client_id():
    while True:
        new_client_id = "client_" + ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        if new_client_id not in active_clients:
            return new_client_id
