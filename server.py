from db import (
    authenticate,
    create,
    create_chatroom,
    chatroom_exists,
    chatroom_name,
    update_chatroom,
)
from chatroom import Chatroom
from message import Message
import json, socket, threading


def not_none(d, keys):
    return False not in [d.get(key) is not None for key in keys]


class Server:
    def __init__(self, host: str, port: int, backlog: int = 10, bufsize: int = 1024):
        self.host = host
        self.port = port
        self.backlog = backlog
        self.bufsize = bufsize
        self.chatrooms = {}
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind((self.host, self.port))

    def close(self):
        """
        Close socket.
        """

        try:
            self.socket.shutdown(socket.SHUT_RDWR)
        except:
            pass

    def listen(self):
        self.socket.listen(self.backlog)
        while True:
            client, address = self.socket.accept()
            client.settimeout(60)
            threading.Thread(target=self.receive, args=(client, address)).start()

    def receive(self, client, address):
        try:
            fragments = []
            while True:
                chunk = client.recv(self.bufsize)
                fragments.append(chunk)
                if len(chunk) < self.bufsize:
                    break
            self.respond(
                client, address, json.loads((b"".join(fragments)).decode("ascii"))
            )
        except Exception as e:
            self.send(client, {"code": 500, "reason": str(e)})

    def respond(self, client, address, data):
        if data.get("route") == "auth" and not_none(data, ["username", "password"]):
            status = authenticate(data["username"], data["password"])
            self.send(client, {"code": 200, "status": status})
            return
        elif data.get("route") == "signup" and not_none(data, ["username", "password"]):
            uuid = create(data["username"], data["password"])
            self.send(client, {"code": 200, "uuid": uuid})
            return
        elif data.get("route") == "create" and not_none(
            data, ["username", "password", "name"]
        ):
            if not authenticate(data["username"], data["password"]):
                self.send(client, {"code": 500, "reason": "Invalid authentication"})
                return
            chatroom_id = create_chatroom(data["name"])
            self.chatrooms[chatroom_id] = Chatroom(data["name"], chatroom_id, [client])
            self.send(client, {"code": 200, "chatroom_id": chatroom_id})
            return
        elif data.get("route") == "join" and not_none(
            data, ["username", "password", "chatroom_id"]
        ):
            if not authenticate(data["username"], data["password"]):
                self.send(client, {"code": 500, "reason": "Invalid authentication"})
                return
            if data["chatroom_id"] in self.chatrooms.keys():
                self.chatrooms[data["chatroom_id"]].connections.append(client)
                self.send(
                    client,
                    {"code": 200, "msgs": self.chatrooms[data["chatroom_id"]].messages},
                )
            else:
                if not chatroom_exists(data["chatroom_id"]):
                    self.send(client, {"code": 500, "reason": "Chatroom doesn't exist"})
                    return
                # Add to server chatrooms that are open
                self.chatrooms[data["chatroom_id"]] = Chatroom(
                    chatroom_name(data["chatroom_id"]), data["chatroom_id"], [client]
                )
                self.send(
                    client,
                    {"code": 200, "msgs": self.chatrooms[data["chatroom_id"]].messages},
                )
                return
        elif data.get("route") == "chat" and not_none(
            data, ["username", "password", "chatroom_id", "msg"]
        ):
            status = authenticate(data["username"], data["password"])
            if not status:
                self.send(client, {"code": 500, "reason": "Invalid authentication"})
                return
            new = Message(data["username"], data["msg"], data["chatroom_id"])
            self.chatrooms[data["chatroom_id"]].add_message(new)
            # Need to send out to server
            update_chatroom(
                data["chatroom_id"], self.chatrooms[data["chatroom_id"]].messages
            )
            for connection in self.chatrooms[data["chatroom_id"]]:
                connection.send(json.dumps({"new": new}))
            self.send(client, {"code": 200})
            return
        self.send(client, {"code": 404, "reason": "Not Found"})

    def send(self, client, data: dict):
        client.send(json.dumps(data).encode())


def available_port(start: int, max_search: int = 10):
    """
    Test for available ports, starting from given argument.

    Parameters:
        start (int)

    Returns:
        available (int)
    """

    available = start
    query = 0
    while query < max_search:
        # Search for available ports
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("0.0.0.0", available))
            s.close()
            return available
        except:
            s.close()
            available += 1
            query += 1
    raise Exception(f"Unable to find available port from range {start} to {available}.")
