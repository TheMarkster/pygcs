#!/usr/bin/env python3
"""
Event Bridge Client - Connects to the Event Bridge Server and synchronizes events.
"""

import socket
import threading
import time
from pygcs.event_bus import EventHandler, Event, broadcast, events, local_broadcast, Broadcastable
from pygcs.signals import GlobalSignals
from pygcs.networking import read_message, write_message, Message
import argparse

class EventBridgeClient(Broadcastable, EventHandler):
    def __init__(self, server_host='localhost', server_port=8888, client_name=None):
        client_name = client_name or f"Client-{int(time.time())}"
        Broadcastable.__init__(self)
        EventHandler.__init__(self, f"event_bridge_client_{client_name}")
        
        self.server_host = server_host
        self.server_port = server_port
        self.client_name = client_name
        self.socket = None
        self.connected = False
        self.running = False
        
        # Forward all events to the local broadcaster
        events.forward_to(self)
        self.forward_to(events)
        
        broadcast(GlobalSignals.LOG, f"🔌 Event Bridge Client '{self.client_name}' initialized")
    
    def connect(self):
        """Connect to the Event Bridge Server"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.server_host, self.server_port))
            self.connected = True
            self.running = True
            
            broadcast(GlobalSignals.LOG, f"🔗 Connected to Event Bridge Server at {self.server_host}:{self.server_port}")
            
            # Start listening for events from server
            worker_thread = threading.Thread(target=self._listen_for_events, daemon=True)
            worker_thread.start()

            return True
            
        except Exception as e:
            broadcast(GlobalSignals.LOG, f"❌ Failed to connect to server: {e}")
            self.connected = False
            return False
    
    def _listen_for_events(self):
        """Listen for events from the server"""
        while self.running and self.connected:
            try:
                message = read_message(self.socket)
                if not message:
                    local_broadcast(GlobalSignals.LOG, "📡 Server disconnected")
                    break
                
                if message.content == 'event':
                    try:
                        event = Event.from_dict(message.data)
                        event.push_path(f"{self.server_host}:{self.server_port}")
                        self.receive(event)
                    except Exception as e:
                        local_broadcast(GlobalSignals.LOG, f"❌ Error processing event from server: {e}")
                else:
                    local_broadcast(GlobalSignals.LOG, f"❌ Unknown message type from server: {message.content}")
                        
            except Exception as e:
                if self.running:
                    local_broadcast(GlobalSignals.LOG, f"❌ Error receiving from server: {e}")
                break
        
        self.connected = False
        local_broadcast(GlobalSignals.LOG, f"📡 Client '{self.client_name}' disconnected from server")
    
    def process(self, event: Event) -> Event:
        """Forward local events to the server"""
        if not self.connected:
            return event
            
        # Get the device list to avoid sending back to devices that have already seen this event
        devices, _ = event.get_path_data()
        server_address = f"{self.server_host}:{self.server_port}"
        
        if server_address in devices:
            # Don't send back to the server if it has already seen this event
            # local_broadcast(GlobalSignals.LOG, f"📡 Skipping '{event.signal}' to server (already seen)")
            return event
        
        message = Message(
            content='event',
            data=event.to_dict()
        )
        
        try:
            write_message(self.socket, message)
            # local_broadcast(GlobalSignals.LOG, f"📤 Sent '{event.signal}' to server")
        except Exception as e:
            local_broadcast(GlobalSignals.LOG, f"❌ Failed to send event to server: {e}")
            self.connected = False
        
        return event
    
    @events.consumer(GlobalSignals.DISCONNECTED)
    def disconnect(self):
        if not self.running and not self.connected:
            return
        
        """Disconnect from the server"""
        broadcast(GlobalSignals.LOG, f"🔌 Disconnecting client '{self.client_name}'...")
        self.running = False
        self.connected = False
        
        if self.socket:
            try:
                self.socket.close()
            except:
                pass

def main():
    """Main client entry point"""
    import sys
    
    # Allow client name to be specified as command line argument
    parser = argparse.ArgumentParser(description="Event Bridge Client")
    parser.add_argument('--host', type=str, default='localhost', help="Event Bridge Server host")
    parser.add_argument('--port', type=int, default=8889, help="Event Bridge Server port")
    args = parser.parse_args()

    client = EventBridgeClient(server_host=args.host, server_port=args.port)
    
    try:
        # Start client in a separate thread
        client.start()
        time.sleep(1)  # Give it a moment to connect
        
        # Add some test event handlers
        @events.consumer('user_action')
        def handle_user_action(action, user=None, **kwargs):
            broadcast(GlobalSignals.LOG, f"🎯 Client received user_action: {user} {action}")
        
        @events.consumer('system_status')
        def handle_system_status(status, component=None, **kwargs):
            broadcast(GlobalSignals.LOG, f"📊 Client received system_status: {component} is {status}")
        
        lock = threading.Lock()
        @events.consumer(GlobalSignals.LOG)
        def handle_log(message, **kwargs):
            with lock:
                print(f"📜 {message}")

        # Generate some test events
        def generate_test_events():
            time.sleep(3)  # Wait a bit before starting
            for i in range(3):
                broadcast('user_action', action='logout', user=f'{client.client_name}-User{i}')
                time.sleep(3)
                broadcast('system_status', status='warning', component=f'{client.client_name}-Service{i}')
                time.sleep(3)
        
        test_thread = threading.Thread(target=generate_test_events, daemon=True)
        test_thread.start()
        
        broadcast(GlobalSignals.LOG, f"🔥 Event Bridge Client '{client.client_name}' running. Press Ctrl+C to stop.")
        broadcast(GlobalSignals.LOG, "📡 Events will be synchronized with server and other clients.")
        
        # Keep the main thread alive
        while client.running:
            time.sleep(1)
            
    except KeyboardInterrupt:
        broadcast(GlobalSignals.LOG, f"\n🛑 Shutting down client '{client.client_name}'...")
    finally:
        client.disconnect()

if __name__ == "__main__":
    main()
