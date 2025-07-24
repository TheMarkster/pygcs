# from pygcs.controller import GRBLController
# from pygcs.serial_comm import GRBLSerial
from pygcs.pretty_terminal import PrettyTerminal
from pygcs.event_bridge_client import EventBridgeClient
from pygcs.event_bus import events, broadcast
from pygcs.signals import GlobalSignals
import threading
import time

def main():
    """Main client entry point"""
    import sys


    # @events.consumer(GlobalSignals.DISCONNECTED)
    # def handle_disconnect():
    #     nonlocal running
    #     running = False

    pretty_terminal = PrettyTerminal()
    pretty_terminal.start()
    
    # Allow client name to be specified as command line argument
    # client_name = sys.argv[1] if len(sys.argv) > 1 else None
    client_name = "Bob's Your Uncle"
    server_host = "localhost"
    server_port = 8889

    client = EventBridgeClient(server_host=server_host, server_port=server_port)
    
    # Try to connect to server
    if not client.connect():
        broadcast(GlobalSignals.LOG, "❌ Could not connect to server. Make sure the Event Bridge Server is running.")
        return
    
    try:
        # Add some test event handlers
        
        # Generate some test events
        # def generate_test_events():
        #     time.sleep(3)  # Wait a bit before starting
        #     for i in range(3):
        #         broadcast(GlobalSignals.LOG, "📡 Hello from the other side")
        
        # test_thread = threading.Thread(target=generate_test_events, daemon=True)
        # test_thread.start()

        # @events.consumer(GlobalSignals.USER_INPUT)
        # def handle_user_input(user_input, **kwargs):
        #     broadcast(GlobalSignals.LOG, f"🎯 Client terminal says: {user_input}")
        
        @events.consumer(GlobalSignals.USER_INPUT)
        def log(message):
            broadcast(GlobalSignals.LOG, f"📜 {message}")

        @events.consumer(GlobalSignals.USER_RESPONSE)
        def handle_user_response(response, **kwargs):
            broadcast(GlobalSignals.LOG, f"📬 Client response: {response}")
        
        # broadcast(GlobalSignals.LOG, f"🔥 Event Bridge Client '{client.client_name}' running. Press Ctrl+C to stop.")
        # broadcast(GlobalSignals.LOG, "📡 Events will be synchronized with server and other clients.")
        
        # Keep the main thread alive
        while client.running:
            time.sleep(1)
            
    except KeyboardInterrupt:
        broadcast(GlobalSignals.LOG, f"\n🛑 Shutting down client '{client.client_name}'...")

if __name__ == "__main__":
    main()
