"""
Example usage of the APIObject as MessageProcessor
"""

from pygcs.api_server import APIObject, api_method, client_method, server_method
from pygcs.networking.server_client import Server, Client
import time
import threading

class CalculatorAPI(APIObject):
    """Example API that can work as both client and server"""
    
    def __init__(self):
        super().__init__("calculator_api")
        self.stored_value = 0
    
    @api_method("add")
    def add_numbers(self, a: float, b: float) -> float:
        """Add two numbers - available on both client and server"""
        result = a + b
        print(f"Adding {a} + {b} = {result}")
        return result
    
    @api_method("multiply")
    def multiply_numbers(self, a: float, b: float) -> float:
        """Multiply two numbers"""
        result = a * b
        print(f"Multiplying {a} * {b} = {result}")
        return result
    
    @api_method("store")
    @server_method
    def store_value(self, value: float) -> str:
        """Store a value on the server - server only"""
        self.stored_value = value
        print(f"Stored value: {value}")
        return f"Stored {value}"
    
    @api_method("get_stored")
    @server_method
    def get_stored_value(self) -> float:
        """Get stored value - server only"""
        print(f"Retrieved stored value: {self.stored_value}")
        return self.stored_value
    
    @api_method("ping")
    def ping(self) -> str:
        """Simple ping method"""
        return "pong"

def run_server():
    """Run the calculator as a server"""
    print("=== Starting Calculator Server ===")
    
    # Create server and API
    server = Server(host='localhost', port=8888)
    calc_api = CalculatorAPI()
    
    # Attach API to server
    server.add_processor(calc_api)
    
    try:
        # Start server
        success = server.connect()
        if not success:
            print("❌ Failed to start server")
            return
            
        print("✅ Calculator server started on localhost:8888")
        
        # Keep server running
        print("Server running... Press Ctrl+C to stop")
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n🛑 Stopping server...")
    except Exception as e:
        print(f"❌ Server error: {e}")
    finally:
        server.stop()
        print("Server stopped")

def run_client():
    """Run the calculator as a client"""
    print("=== Starting Calculator Client ===")
    
    # Create client and API
    client = Client(server_host='localhost', server_port=8888)
    calc_api = CalculatorAPI()
    
    # Attach API to client
    client.add_processor(calc_api)
    
    try:
        # Connect to server
        success = client.connect()
        if not success:
            print("❌ Failed to connect to server")
            return
            
        print("✅ Connected to calculator server")
        
        # Wait a moment for connection to establish
        time.sleep(0.5)
        
        # Test basic math operations
        print("\n--- Testing Math Operations ---")
        result1 = calc_api.call_remote("add", 5, 3)
        print(f"5 + 3 = {result1}")
        
        result2 = calc_api.call_remote("multiply", 4, 7)
        print(f"4 * 7 = {result2}")
        
        # Test ping
        print("\n--- Testing Ping ---")
        pong = calc_api.call_remote("ping")
        print(f"Ping response: {pong}")
        
        # Test server-only methods
        print("\n--- Testing Server Storage ---")
        store_result = calc_api.call_remote("store", 42.5)
        print(f"Store result: {store_result}")
        
        stored_value = calc_api.call_remote("get_stored")
        print(f"Retrieved value: {stored_value}")
        
        # Test async calls
        print("\n--- Testing Async Calls ---")
        future1 = calc_api.call_remote_async("add", 10, 20)
        future2 = calc_api.call_remote_async("multiply", 6, 9)
        
        # Wait for results
        async_result1 = future1.result(timeout=5.0)
        async_result2 = future2.result(timeout=5.0)
        
        print(f"Async add result: {async_result1.result}")
        print(f"Async multiply result: {async_result2.result}")
        
        # Test error handling
        print("\n--- Testing Error Handling ---")
        try:
            calc_api.call_remote("nonexistent_method")
        except RuntimeError as e:
            print(f"Expected error: {e}")
        
    except Exception as e:
        print(f"❌ Client error: {e}")
    finally:
        client.stop()
        print("Client disconnected")

def run_standalone_usage():
    """Demonstrate standalone usage (no networking)"""
    print("=== Standalone Usage ===")
    
    calc = CalculatorAPI()
    
    # Use methods directly (no networking)
    result1 = calc.add_numbers(15, 25)
    print(f"Standalone add: {result1}")
    
    result2 = calc.multiply_numbers(8, 12)
    print(f"Standalone multiply: {result2}")
    
    calc.store_value(100)
    stored = calc.get_stored_value()
    print(f"Standalone storage: {stored}")

def run_multi_api_server():
    """Demonstrate multiple APIs on one server"""
    print("=== Multi-API Server ===")
    
    # Create server
    server = Server(host='localhost', port=8889)
    
    # Create multiple APIs
    calc_api = CalculatorAPI()
    
    class StringAPI(APIObject):
        def __init__(self):
            super().__init__("string_api")
        
        @api_method("reverse")
        def reverse_string(self, text: str) -> str:
            return text[::-1]
        
        @api_method("upper")
        def uppercase(self, text: str) -> str:
            return text.upper()
    
    string_api = StringAPI()
    
    # Attach both APIs to server
    server.add_processor(calc_api)
    server.add_processor(string_api)
    
    try:
        success = server.connect()
        if not success:
            print("❌ Failed to start multi-API server")
            return
            
        print("✅ Multi-API server started on localhost:8889")
        print("Available APIs: calculator_api, string_api")
        
        print("Server running... Press Ctrl+C to stop")
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n🛑 Stopping multi-API server...")
    except Exception as e:
        print(f"❌ Server error: {e}")
    finally:
        server.stop()
        print("Multi-API server stopped")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python api_example.py server      # Run as server")
        print("  python api_example.py client      # Run as client")
        print("  python api_example.py standalone  # Run standalone")
        print("  python api_example.py multi       # Run multi-API server")
        sys.exit(1)
    
    mode = sys.argv[1].lower()
    
    if mode == "server":
        run_server()
    elif mode == "client":
        run_client()
    elif mode == "standalone":
        run_standalone_usage()
    elif mode == "multi":
        run_multi_api_server()
    else:
        print(f"Unknown mode: {mode}")
        sys.exit(1)
