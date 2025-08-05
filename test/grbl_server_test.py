from __future__ import annotations

from pygcs.networking import Client, Server, MessageProcessor, Message
from pygcs.remote_objects import RemoteObject, RemoteObjectServer, ClientProcessor
from dataclasses import dataclass
import socket
from concurrent.futures import Future, ThreadPoolExecutor
import threading
from typing import Dict, List, Literal, Any
from functools import wraps
from pygcs.controller import GRBLController

class TestClass:
    def __init__(self):
        self.value = "Test Value"

    @property
    def test_property(self):
        return self.value

    @test_property.setter
    def test_property(self, value):
        self.value = value
        
    def test_method(self, arg1, arg2):
        return f"Method called with {arg1} and {arg2}"


def main():
    """Run the remote object server"""
    print("=== Testing Base Remote Call Classes ===")

    # client_host = "localhost"
    server_host = "0.0.0.0"
    port = 8889
    server = Server(host=server_host, port=port)

    if not server.connect():
        print("❌ Could not start server. Make sure the port is available.")
        return
    
    remote_object_server = RemoteObjectServer()
    server.add_processor(remote_object_server)

    controller = GRBLController()
    obj_id = remote_object_server.register_object(controller)
    print(f"✅ Registered controller object with ID: {obj_id}")

    print(f"✅ Server running on {server_host}:{port}")

    # Test the server briefly
    import time
    time.sleep(1)

    try:
        while server.running:
            time.sleep(1)  # Keep server running
    except KeyboardInterrupt:
        print("🛑 Stopping server...")
        server.stop()

if __name__ == "__main__":
    main()