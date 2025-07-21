#!/usr/bin/env python3
"""
Event Bridge Client - Connects to the Event Bridge Server and synchronizes events.
"""

import socket
import threading
import json
import time
from broadcast import get_broadcast, Broadcastable

class EventBridgeClient(Broadcastable):
    def __init__(self, server_host='localhost', server_port=8888, client_name=None):
        super().__init__(namespace='event_bridge_client')
        self.server_host = server_host
        self.server_port = server_port
        self.client_name = client_name or f"Client-{int(time.time())}"
        self.socket = None
        self.connected = False
        self.running = False
        self.broadcast = get_broadcast()
        
        # Add watcher to capture all local events and send to server
        self.broadcast.add_watcher(self._forward_event_to_server)
        
        print(f"Event Bridge Client '{self.client_name}' initialized")
    
    def connect(self):
        """Connect to the Event Bridge Server"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.server_host, self.server_port))
            self.connected = True
            self.running = True
            
            print(f"🔗 Connected to Event Bridge Server at {self.server_host}:{self.server_port}")
            
            # Start listening for events from server
            listen_thread = threading.Thread(target=self._listen_for_events, daemon=True)
            listen_thread.start()
            
            return True
            
        except Exception as e:
            print(f"❌ Failed to connect to server: {e}")
            self.connected = False
            return False
    
    def _listen_for_events(self):
        """Listen for events from the server"""
        while self.running and self.connected:
            try:
                data = self.socket.recv(4096)
                if not data:
                    print("📡 Server disconnected")
                    break
                
                try:
                    # Parse the received event
                    event_data = json.loads(data.decode('utf-8'))
                    signal = event_data.get('signal')
                    args = event_data.get('args', [])
                    kwargs = event_data.get('kwargs', {})
                    
                    print(f"📨 Received from server: {signal}")
                    
                    # Broadcast the event locally (but mark it as remote to avoid echo)
                    kwargs['_remote_event'] = True
                    kwargs['_source_address'] = 'server'
                    self.broadcast.emit(signal, *args, **kwargs)
                    
                except json.JSONDecodeError as e:
                    print(f"❌ Invalid JSON from server: {e}")
                except Exception as e:
                    print(f"❌ Error processing event from server: {e}")
                    
            except socket.error as e:
                if self.running:
                    print(f"❌ Socket error: {e}")
                break
            except Exception as e:
                print(f"❌ Unexpected error: {e}")
                break
        
        self.connected = False
    
    def _forward_event_to_server(self, signal, *args, **kwargs):
        """Forward local events to the server"""
        if not self.connected:
            return
        
        # Don't forward remote events back (avoid loops)
        if kwargs.get('_remote_event'):
            return
        
        # Don't forward internal client events
        if signal.startswith('instance_') or signal.startswith('broadcast_'):
            return
        
        # Prepare event data for transmission
        event_data = {
            'signal': signal,
            'args': args,
            'kwargs': {k: v for k, v in kwargs.items() if not k.startswith('_')}
        }
        
        try:
            message = json.dumps(event_data).encode('utf-8')
            self.socket.send(message)
            print(f"📤 Sent '{signal}' to server")
        except Exception as e:
            print(f"❌ Failed to send event to server: {e}")
            self.connected = False
    
    def disconnect(self):
        """Disconnect from the server"""
        print(f"🔌 Disconnecting client '{self.client_name}'...")
        self.running = False
        self.connected = False
        
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
        
        # Remove watcher
        self.broadcast.remove_watcher(self._forward_event_to_server)

def main():
    """Main client entry point"""
    import sys
    
    # Allow client name to be specified as command line argument
    client_name = sys.argv[1] if len(sys.argv) > 1 else None
    
    client = EventBridgeClient(client_name=client_name)
    
    # Try to connect to server
    if not client.connect():
        print("❌ Could not connect to server. Make sure the Event Bridge Server is running.")
        return
    
    try:
        # Add some test event handlers
        broadcast = get_broadcast()
        
        @broadcast.consumer('user_action')
        def handle_user_action(action, user=None, **kwargs):
            source = kwargs.get('_source_address', 'local')
            print(f"🎯 Client received user_action: {user} {action} (from {source})")
        
        @broadcast.consumer('system_status')
        def handle_system_status(status, component=None, **kwargs):
            source = kwargs.get('_source_address', 'local')
            print(f"📊 Client received system_status: {component} is {status} (from {source})")
        
        # Generate some test events
        def generate_test_events():
            time.sleep(3)  # Wait a bit before starting
            for i in range(3):
                broadcast.emit('user_action', action='logout', user=f'{client.client_name}-User{i}')
                time.sleep(3)
                broadcast.emit('system_status', status='warning', component=f'{client.client_name}-Service{i}')
                time.sleep(3)
        
        test_thread = threading.Thread(target=generate_test_events, daemon=True)
        test_thread.start()
        
        print(f"🔥 Event Bridge Client '{client.client_name}' running. Press Ctrl+C to stop.")
        print("📡 Events will be synchronized with server and other clients.")
        
        # Keep the main thread alive
        while client.connected:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print(f"\n🛑 Shutting down client '{client.client_name}'...")
    finally:
        client.disconnect()

if __name__ == "__main__":
    main()
