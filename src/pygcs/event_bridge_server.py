#!/usr/bin/env python3
"""
Event Bridge Server - Receives events from clients and broadcasts them to all connected clients.
"""

import socket
import threading
import json
import time
from pygcs.broadcast import get_broadcast, Broadcastable
from .signals import signals
from .broadcast import broadcast

class EventBridgeServer(threading.Thread, Broadcastable):
    def __init__(self, host='localhost', port=8888):
        Broadcastable.__init__(self, namespace='event_bridge')
        threading.Thread.__init__(self, daemon=True)
        
        self.host = host
        self.port = port
        self.clients = []  # List of client sockets
        self.running = False
        self.server_socket = None
        self.broadcast = get_broadcast()
        
        # Add watcher to capture all local events and send to clients
        self.broadcast.add_watcher(self._forward_event_to_clients)
        
        signals.LOG.emit(f"Event Bridge Server initialized on {host}:{port}")
    
    def run(self):
        """Start the server and listen for client connections"""
        self.running = True
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.settimeout(1)
        
        try:
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)
            signals.LOG.emit(f"🌐 Event Bridge Server listening on {self.host}:{self.port}")
            
            while self.running:
                try:
                    client_socket, address = self.server_socket.accept()
                    signals.LOG.emit(f"📡 Client connected from {address}")
                    
                    # Start a thread to handle this client
                    client_thread = threading.Thread(
                        target=self._handle_client,
                        args=(client_socket, address),
                        daemon=True
                    )
                    client_thread.start()
                
                except socket.timeout:
                    continue
                except socket.error as e:
                    if self.running:
                        signals.LOG.emit(f"❌ Server error: {e}")
                    break
                
        except Exception as e:
            signals.LOG.emit(f"❌ Failed to start server: {e}")
        finally:
            self._cleanup()
    
    def _handle_client(self, client_socket, address):
        """Handle communication with a connected client"""
        self.clients.append(client_socket)
        
        try:
            while self.running:
                # Receive data from client
                data = client_socket.recv(4096)
                if not data:
                    break
                
                try:
                    # Parse the received event
                    event_data = json.loads(data.decode('utf-8'))
                    signal = event_data.get('signal')
                    args = event_data.get('args', [])
                    kwargs = event_data.get('kwargs', {})
                    
                    signals.LOG.emit(f"📨 Received from {address}: {signal}")
                    
                    # Broadcast the event locally (but mark it as remote to avoid echo)
                    kwargs['_remote_event'] = True
                    kwargs['_source_address'] = str(address)
                    self.broadcast.emit(signal, *args, **kwargs)
                    
                except json.JSONDecodeError as e:
                    signals.LOG.emit(f"❌ Invalid JSON from {address}: {e}")
                except Exception as e:
                    signals.LOG.emit(f"❌ Error processing event from {address}: {e}")
                    
        except Exception as e:
            signals.LOG.emit(f"❌ Client {address} error: {e}")
        finally:
            # Clean up client connection
            if client_socket in self.clients:
                self.clients.remove(client_socket)
            try:
                client_socket.close()
            except:
                pass
            signals.LOG.emit(f"📡 Client {address} disconnected")
    
    def _forward_event_to_clients(self, signal, *args, **kwargs):
        """Forward local events to all connected clients"""
        # Don't forward remote events back (avoid loops)
        if kwargs.get('_remote_event'):
            return
        
        # Don't forward internal server events
        if signal.startswith('instance_') or signal.startswith('broadcast_'):
            return
        
        # Prepare event data for transmission
        event_data = {
            'signal': signal,
            'args': args,
            'kwargs': {k: v for k, v in kwargs.items() if not k.startswith('_')}
        }
        
        message = json.dumps(event_data).encode('utf-8')
        
        # Send to all connected clients
        disconnected_clients = []
        for client in self.clients:
            try:
                client.send(message)
                signals.LOG.emit(f"📤 Forwarded '{signal}' to client")
            except Exception as e:
                signals.LOG.emit(f"❌ Failed to send to client: {e}")
                disconnected_clients.append(client)
        
        # Remove disconnected clients
        for client in disconnected_clients:
            if client in self.clients:
                self.clients.remove(client)
    
    @broadcast.consumer(signals.DISCONNECTED)
    def stop(self):
        """Stop the server"""
        signals.LOG.emit("🛑 Stopping Event Bridge Server...")
        self.running = False
        
        # Close all client connections
        for client in self.clients:
            try:
                client.close()
            except:
                pass
        
        # Close server socket
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
        pass
    
    def _cleanup(self):
        """Clean up server resources"""
        broadcast.remove_watcher(self._forward_event_to_clients)
        if self.running:
            self.stop()

def main():
    """Main server entry point"""
    server = EventBridgeServer()
    
    try:
        # Start server in a separate thread
        server.start()
        
        # Add some test event handlers
        broadcast = get_broadcast()
        
        @broadcast.consumer('user_action')
        def handle_user_action(action, user=None, **kwargs):
            source = kwargs.get('_source_address', 'local')
            signals.LOG.emit(f"🎯 Server received user_action: {user} {action} (from {source})")
        
        @broadcast.consumer('system_status')
        def handle_system_status(status, component=None, **kwargs):
            source = kwargs.get('_source_address', 'local')
            signals.LOG.emit(f"📊 Server received system_status: {component} is {status} (from {source})")
        
        # Generate some test events
        def generate_test_events():
            time.sleep(2)  # Wait for server to start
            for i in range(3):
                broadcast.emit('user_action', action='login', user=f'ServerUser{i}')
                time.sleep(2)
                broadcast.emit('system_status', status='healthy', component=f'Service{i}')
                time.sleep(2)
        
        test_thread = threading.Thread(target=generate_test_events, daemon=True)
        test_thread.start()
        
        signals.LOG.emit("🔥 Event Bridge Server running. Press Ctrl+C to stop.")
        signals.LOG.emit("📡 Clients can connect and events will be synchronized.")
        
        # Keep the main thread alive
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        signals.LOG.emit("\n🛑 Shutting down server...")
        server.stop()

if __name__ == "__main__":
    main()
