#!/usr/bin/env python3
"""Mock WebSocket server — pushes a fake graph node every 500ms.

Usage:
    python scripts/mock_graph_server.py [--port 8765]
"""
import argparse
import asyncio
import json
import random
import string
import uuid
from datetime import datetime

try:
    import websockets
    from websockets.server import WebSocketServerProtocol
except ImportError:
    raise SystemExit("Install websockets: pip install websockets")

NODE_TYPES = [
    "Commit", "File", "Symbol", "PR", "Issue",
    "Discussion", "Decision", "Person", "Repository",
]

LABEL_PREFIXES: dict[str, list[str]] = {
    "Commit": ["feat:", "fix:", "refactor:", "docs:", "test:"],
    "File": ["src/", "lib/", "tests/", "docs/"],
    "Symbol": ["fn_", "struct_", "impl_", "trait_"],
    "PR": ["#"],
    "Issue": ["#"],
    "Discussion": ["thread:"],
    "Decision": ["dec:"],
    "Person": ["@"],
    "Repository": ["repo:"],
}


def rand_id() -> str:
    return uuid.uuid4().hex[:8]


def rand_label(node_type: str) -> str:
    prefix = random.choice(LABEL_PREFIXES.get(node_type, [""]))
    suffix = "".join(random.choices(string.ascii_lowercase, k=random.randint(4, 10)))
    return f"{prefix}{suffix}"


class MockServer:
    def __init__(self) -> None:
        self.clients: set[WebSocketServerProtocol] = set()
        self.all_node_ids: list[str] = []

    async def register(self, ws: WebSocketServerProtocol) -> None:
        self.clients.add(ws)
        print(f"[{datetime.now():%H:%M:%S}] client connected ({len(self.clients)} total)")

    async def unregister(self, ws: WebSocketServerProtocol) -> None:
        self.clients.discard(ws)
        print(f"[{datetime.now():%H:%M:%S}] client disconnected ({len(self.clients)} total)")

    async def broadcast(self, msg: dict) -> None:
        if not self.clients:
            return
        data = json.dumps(msg)
        await asyncio.gather(
            *[ws.send(data) for ws in self.clients],
            return_exceptions=True,
        )

    async def handler(self, ws: WebSocketServerProtocol) -> None:
        await self.register(ws)
        try:
            await ws.wait_closed()
        finally:
            await self.unregister(ws)

    async def pusher(self) -> None:
        """Push one new node every 500ms."""
        while True:
            await asyncio.sleep(0.5)
            if not self.clients:
                continue

            node_type = random.choice(NODE_TYPES)
            node_id = rand_id()
            node = {
                "id": node_id,
                "nodeType": node_type,
                "label": rand_label(node_type),
                "val": random.randint(1, 5),
                "superseded": False,
            }
            self.all_node_ids.append(node_id)

            links = []
            if len(self.all_node_ids) > 1:
                n_links = random.randint(0, min(2, len(self.all_node_ids) - 1))
                targets = random.sample(self.all_node_ids[:-1], n_links)
                for t in targets:
                    links.append({"source": node_id, "target": t})

            msg = {"nodes": [node], "links": links}
            await self.broadcast(msg)

            print(
                f"[{datetime.now():%H:%M:%S}] pushed {node_type} {node_id} "
                f"({len(self.all_node_ids)} nodes, {len(links)} new links)"
            )


async def main(port: int) -> None:
    server = MockServer()
    print(f"Mock graph WS server starting on ws://localhost:{port}")
    async with websockets.serve(server.handler, "localhost", port):
        await server.pusher()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    asyncio.run(main(args.port))
