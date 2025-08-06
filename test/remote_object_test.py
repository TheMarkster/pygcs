from __future__ import annotations

from pygcs.networking import Client, Server, MessageProcessor, Message
from pygcs.remote_objects import RemoteObject, RemoteObjectServer, ClientProcessor
from dataclasses import dataclass
import socket
from concurrent.futures import Future, ThreadPoolExecutor
import threading
from typing import Dict, List, Literal, Any
from functools import wraps
import time
import weakref

def serialize(result):
    pass

def deserialize(data):
    pass

class TestObject:
    def __init__(self):
        self.value = "Test Value"
    
    def wait(self):
        time.sleep(1)  # Simulate some wait time
        return True

class TestClass:
    def __init__(self):
        self.value = "Test Value"
        self.test_obj = TestObject()

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

    client_host = "localhost"
    server_host = "0.0.0.0"
    port = 8890
    server = Server(host=server_host, port=port)

    if not server.connect():
        print("❌ Could not start server. Make sure the port is available.")
        return
    
    remote_object_server = RemoteObjectServer()
    remote_object_server.add_allowed_class([TestClass, TestObject])
    remote_object_server.set_strict_mode(False)  # Attribute whitelisting not required for this test
    server.add_processor(remote_object_server)

    test_obj = TestClass()
    obj_id = remote_object_server.register_object(test_obj)
    print(f"✅ Registered test object with ID: {obj_id}")

    print(f"✅ Server running on {server_host}:{port}")

    # Test the server briefly
    import time
    time.sleep(1)

    client = Client(server_host=client_host, server_port=port)

    if not client.connect():
        print("❌ Could not connect to server. Make sure it is running.")
        server.stop()
        return

    api_client = ClientProcessor()
    client.add_processor(api_client)

    # Test API call
    try:
        obj_ids = api_client.call('list_objects', args=[TestClass.__name__])
        print(f"✅ API call successful. Registered objects: {obj_ids}")

        callables = api_client.call('list_callables', args=[obj_ids[0]])
        print(f"✅ Callables for object {obj_ids[0]}: {callables}")
        
        # Test remote object
        if obj_ids:
            remote_obj: TestClass = api_client.get_remote_object(obj_ids[0])
            
            ## Test method call
            # result = remote_obj.test_method("hello", "world")
            # print(f"✅ Remote method call result: {result}")
            
            # # Test property get
            # prop_value = remote_obj.test_property
            # print(f"✅ Remote property get: {prop_value}")
            
            # Test property set
            # remote_obj.test_property = "New Value"
            # new_value = remote_obj.test_property
            # print(f"✅ Remote property set and get: {new_value}")

            # Dynamic object registration
            time.sleep(1) # Let threads settle
            print("Test object")
            test_obj = remote_obj.test_obj
            if test_obj.wait():
                print("✅ Dynamic object call successful")
            del test_obj
            print("✅ Dynamic object registration and wait successful")
            pass
    except Exception as e:
        print(f"❌ Test failed: {e}")

    print("\n🛑 Stopping server and client...")
    server.stop()
    client.stop()
    print("✅ Test completed")

if __name__ == "__main__":
    main()