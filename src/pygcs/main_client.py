# from pygcs.controller import GRBLController
# from pygcs.serial_comm import GRBLSerial
from pygcs.pretty_terminal import PrettyTerminal
from pygcs.event_bridge_client import EventBridgeClient
from pygcs.event_bus import events, broadcast, consumer
from pygcs.signals import GlobalSignals
import threading
import time
import argparse

def main():
    """Main client entry point"""
    # @consumer(GlobalSignals.DISCONNECTED)
    # def handle_disconnect():
    #     nonlocal running
    #     running = False

    pretty_terminal = PrettyTerminal()
    pretty_terminal.start()
    
    # Allow client name to be specified as command line argument
    # client_name = sys.argv[1] if len(sys.argv) > 1 else None
    # client_name = "Bob's Your Uncle"
    # server_host = "localhost"
    # server_port = 8889

    args = argparse.ArgumentParser(description="Event Bridge Client")
    args.add_argument('--host', type=str, default='localhost', help="Event Bridge Server host")
    args.add_argument('--port', type=int, default=8888, help="Event Bridge Server port")
    args = args.parse_args()

    client = EventBridgeClient(server_host=args.host, server_port=args.port)

    # Try to connect to server
    if not client.connect():
        print("❌ Could not connect to server. Make sure the Event Bridge Server is running.")
        return
    
    try:
        # Add some test event handlers
        
        # Generate some test events
        # def generate_test_events():
        #     time.sleep(3)  # Wait a bit before starting
        #     for i in range(3):
        #         print("📡 Hello from the other side")
        
        # test_thread = threading.Thread(target=generate_test_events, daemon=True)
        # test_thread.start()

        # @consumer(GlobalSignals.USER_INPUT)
        # def handle_user_input(user_input, **kwargs):
        #     print(f"🎯 Client terminal says: {user_input}")
        
        @consumer(GlobalSignals.USER_INPUT)
        def log(message):
            print(f"📜 {message}")

        @consumer(GlobalSignals.USER_RESPONSE)
        def handle_user_response(response, **kwargs):
            print(f"📬 Client response: {response}")
        
        # print(f"🔥 Event Bridge Client '{client.client_name}' running. Press Ctrl+C to stop.")
        # print("📡 Events will be synchronized with server and other clients.")
        
        # Keep the main thread alive
        while client.running:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print(f"\n🛑 Shutting down client '{client.client_name}'...")

if __name__ == "__main__":
    main()
