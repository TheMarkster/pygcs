from pygcs.networking.server_client import Client, Server
from pygcs.networking.processor import MessageProcessor
from pygcs.networking.message import Message
from pygcs.event_bus import get_metastate
from pygcs.event_bus import EventHost, events, consumer, intercept_print, broadcast, local_broadcast
from pygcs.signals import GlobalSignals
from pygcs.event_processor import EventProcessor
from pygcs.pretty_terminal import PrettyTerminal
from pygcs.print_interceptor import PrintInterceptor
import time
import argparse

def main():
    parser = argparse.ArgumentParser(description="Start the GCS client")
    parser.add_argument('--host', type=str, default='0.0.0.0', help="Server host")
    parser.add_argument('--port', type=int, default=8888, help="Server port")
    args = parser.parse_args()

    get_metastate()['_debug'] = True  # Enable debug mode for the client

    with PrintInterceptor(intercept_print(GlobalSignals.LOG)): # Convert print messages to events
        threads = []

        terminal = PrettyTerminal()
        terminal.start()
        threads.append(terminal)

        client = Client(
            server_host=args.host,
            server_port=args.port
        )
        client.add_processor(EventProcessor(name='client_event_processor'))

        if client.connect():
            pass
            @consumer(GlobalSignals.DISCONNECTED)
            def handle_disconnect():
                print("❌ Disconnect signal received, shutting down client.")
                client.stop()
            
            @consumer(GlobalSignals.USER_INPUT)
            def handle_user_input(input_text):
                print(input_text)
            
            @consumer(GlobalSignals.USER_RESPONSE)
            def handle_user_response(response_text):
                print(f"User response: {response_text}")

            while client.running:   
                time.sleep(0.5)
            
        local_broadcast(GlobalSignals.DISCONNECTED)  # Broadcast disconnect signal when stopping
        
        for thread in threads:
            thread.join()

if __name__ == "__main__":
    main()