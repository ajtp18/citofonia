// app.js
export const client_id = Math.random().toString(36).substring(7);

export function addMessageToChat(sender, message) {
    const chatDiv = document.getElementById("chat");
    chatDiv.innerHTML += `<p><strong>${sender}: </strong>${message}</p>`;
}

export function sendMessage() {
    const message = document.getElementById("message").value;
    addMessageToChat("You", message);
    ws.send(message);
}

const ws = new WebSocket(`ws://${window.location.host}/ws/${client_id}`);

ws.onmessage = (event) => {
    const message = event.data;
    addMessageToChat("Other user", message);
};

const peer = new SimplePeer({
    initiator: location.hash === "#init",
    trickle: false,
});

peer.on("signal", (data) => {
    ws.send(JSON.stringify(data));
});

peer.on("data", (data) => {
    const message = data.toString();
    const sender = peer.initiator ? "Other user" : "You";
    addMessageToChat(sender, message);
});
