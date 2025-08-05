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
    client_host = "localhost"
    port = 8889

    client = Client(server_host=client_host, server_port=port)

    if not client.connect():
        print("❌ Could not connect to server. Make sure it is running.")
        return

    api_client = ClientProcessor()
    client.add_processor(api_client)

    # Test API call
    try:
        obj_ids = api_client.call('list_objects', args=[TestClass.__name__])
        print(f"✅ API call successful. Registered objects: {obj_ids}")
        
        controller: GRBLController = RemoteObject(obj_ids[0], client)

        
            
    except Exception as e:
        print(f"❌ Test failed: {e}")

    print("\n🛑 Stopping server and client...")
    server.stop()
    client.stop()
    print("✅ Test completed")

if __name__ == "__main__":
    main()