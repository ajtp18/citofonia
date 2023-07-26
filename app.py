from aiortc import RTCConfiguration, RTCIceServer, RTCPeerConnection, RTCSessionDescription, MediaStreamTrack
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import string
import random
import json

app = FastAPI()
connected_peers = {}
active_clients = set()

# Define STUN server
stun_server = RTCIceServer(urls="stun:stun.l.google.com:19302")

configuration = RTCConfiguration(iceServers=[stun_server])

origins = ["*"]

# Agregar el middleware de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class WebSocketRTC:
    def __init__(self, websocket: WebSocket, configuration: RTCConfiguration):
        self.websocket = websocket
        self.configuration = configuration
        self.tracks = []
        self.client_id = None

    async def on_connect(self, client_id: str):
        await self.websocket.accept()
        peer = RTCPeerConnection(configuration=self.configuration)
        connected_peers[client_id] = {"peer": peer, "websocket": self.websocket}
        active_clients.add(client_id)
        self.client_id = client_id

    async def on_receive(self, data: str):
        message = json.loads(data)
        sender_id = message.get("sender_id")
        recipient_id = message.get("recipient_id")
        message_type = message.get("type")

        if message_type == "offer":
            await self.handle_offer(sender_id, RTCSessionDescription(sdp=message["sdp"], type="offer"))
        elif message_type == "answer":
            await self.handle_answer(sender_id, RTCSessionDescription(sdp=message["sdp"], type="answer"))
        elif message_type == "ice-candidate":
            await self.handle_ice_candidate(sender_id, message["candidate"])
        elif message_type == "add-track":
            await self.add_track(sender_id, message["track"])

    async def handle_offer(self, sender_id: str, offer: RTCSessionDescription):
        peer = connected_peers.get(sender_id)
        if not peer:
            return

        await peer["peer"].setRemoteDescription(offer)
        answer_sdp = await peer["peer"].createAnswer()
        await peer["peer"].setLocalDescription(answer_sdp)
        await self.websocket.send_text(json.dumps({
            "type": "answer",
            "recipient_id": sender_id,
            "sdp": answer_sdp.sdp
        }))

    async def handle_answer(self, sender_id: str, answer: RTCSessionDescription):
        peer = connected_peers.get(sender_id)
        if not peer:
            return

        await peer["peer"].setRemoteDescription(answer)

    async def handle_ice_candidate(self, sender_id: str, candidate: dict):
        peer = connected_peers.get(sender_id)
        if not peer:
            return

        candidate = candidate["candidate"]
        if candidate:
            ice_candidate = {"sdpMLineIndex": candidate["sdpMLineIndex"], "sdpMid": candidate["sdpMid"], "candidate": candidate["candidate"]}
            await peer["peer"].addIceCandidate(ice_candidate)

    async def add_track(self, sender_id: str, track: dict):
        # Convert track info received from client to MediaStreamTrack
        track_kind = track["kind"]
        track_id = track["id"]
        track_label = track["label"]
        media_stream_track = MediaStreamTrack(kind=track_kind, id=track_id, label=track_label)

        # Add the track to the PeerConnection
        peer = connected_peers.get(sender_id)
        if not peer:
            return

        await peer["peer"].addTrack(media_stream_track, peer["peer"].getSenders())

        # Store the track in the WebSocketRTC instance to handle cleanup on disconnect
        self.tracks.append(media_stream_track)

    async def send_track(self, recipient_id: str, track: MediaStreamTrack):
        peer = connected_peers.get(recipient_id)
        if not peer:
            return

        # Send the track to the recipient
        sender = peer["peer"].getSenders()[0]  # Assuming there's only one sender
        if sender and sender.track.kind == track.kind:
            sender.replaceTrack(track)

    async def on_disconnect(self, close_code: int):
        client_id = self.client_id

        if client_id:
            # Remove tracks from the PeerConnection to avoid resource leaks
            peer = connected_peers.get(client_id)
            if peer:
                for track in self.tracks:
                    await self.send_track(client_id, track)
                    peer["peer"].removeTrack(track)
            del connected_peers[client_id]
            active_clients.discard(client_id)

            # Notify other clients about the disconnection
            disconnection_message = json.dumps({
                "type": "disconnection",
                "client_id": client_id
            })
            await self.broadcast(disconnection_message)

    async def broadcast(self, message: str):
        # Send a message to all connected clients except the current one
        for client_id, peer in connected_peers.items():
            if client_id != self.client_id:
                await peer["websocket"].send_text(message)

@app.get("/")
async def read_index():
    client_id = generate_unique_client_id()
    return {"client_id": client_id}

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
