#!/usr/bin/env python3
"""
Event Bridge Server - Receives events from clients and broadcasts them to all connected clients.
"""
from __future__ import annotations

import socket
import threading
import time
from pygcs.event_bus import EventHandler, Event, broadcast, local_broadcast
from pygcs.signals import GlobalSignals
from pygcs.event_bus import events
from pygcs.networking import read_message, write_message, Message

class EventBridgeServer(threading.Thread, EventHandler):
    def __init__(self, host='localhost', port=8888):
        EventHandler.__init__(self, f"event_bridge_server_{host}_{port}")
        threading.Thread.__init__(self, daemon=True)
        
        self.host = host
        self.port = port
        self._clients = []  # List of client sockets
        self.running = False
        self.server_socket = None

        # Forward all events to the local broadcaster
        events.forward_to(self)
        self.forward_to(events)
    
    @property
    def clients(self) -> list[socket.socket]:
        return self._clients
    
    def run(self):
        """Start the server and listen for client connections"""
        self.running = True
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.settimeout(1)
        
        try:
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)
            broadcast(GlobalSignals.LOG, f"🌐 Event Bridge Server listening on {self.host}:{self.port}")
            
            while self.running:
                try:
                    client_socket, address = self.server_socket.accept()
                    broadcast(GlobalSignals.LOG, f"📡 Client connected from {address}")
                    
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
                        broadcast(GlobalSignals.LOG, f"❌ Server error: {e}")
                    break
                
        except Exception as e:
            broadcast(GlobalSignals.LOG, f"❌ Failed to start server: {e}")
        finally:
            self._cleanup()
        
    def get_path_name(self, client_socket: socket.socket) -> str:
        """Get a string representation of the client address"""
        try:
            return str(client_socket.getpeername())
        except:
            return "unknown"
    
    def _handle_client(self, client_socket: socket.socket, address: tuple):
        """Handle communication with a connected client"""
        self.clients.append(client_socket)
        
        try:
            while self.running:
                # Receive data from client
                try:
                    message = read_message(client_socket)
                    if not message:
                        local_broadcast(GlobalSignals.LOG, f"📡 Client {address} disconnected")
                        break
                except Exception as e:
                    local_broadcast(GlobalSignals.LOG, f"❌ Error reading from {address}: {e}")
                    break

                match message.content:
                    case 'event':
                        try:
                            event = Event.from_dict(message.data)
                            event.push_path(self.get_path_name(client_socket))
                            self.receive(event)
                            local_broadcast(GlobalSignals.LOG, f"📤 Received signal '{event.signal}' and message '{event.args}' from {address}")
                        except Exception as e:
                            local_broadcast(GlobalSignals.LOG, f"❌ Error processing event from {address}: {e}")
                    case _:
                        local_broadcast(GlobalSignals.LOG, f"❌ Unknown message type from {address}: {message.content}")
                        continue

        except Exception as e:
            local_broadcast(GlobalSignals.LOG, f"❌ Client {address} error: {e}")
        finally:
            # Clean up client connection
            if client_socket in self.clients:
                self.clients.remove(client_socket)
            try:
                client_socket.close()
            except:
                pass
            local_broadcast(GlobalSignals.LOG, f"📡 Client {address} disconnected")
    
    def process(self, event: Event) -> Event:
        """Forward local events to all connected clients"""
        message = Message(
            content='event',
            data=event.to_dict()
        )
        
        # Get the device list to avoid sending back to devices that have already seen this event
        devices, _ = event.get_path_data()
        
        # Send to all connected clients
        disconnected_clients = []
        for client in self.clients:
            address = self.get_path_name(client)
            if address in devices:
                # Don't send back to devices that have already seen this event
                # local_broadcast(GlobalSignals.LOG, f"📡 Skipping '{event.signal}' to {address} (already seen)")
                continue

            try:
                write_message(client, message)
                local_broadcast(GlobalSignals.LOG, f"📤 Forwarded '{event.signal}' to client {address}")
            except Exception as e:
                local_broadcast(GlobalSignals.ERROR, f"❌ Failed to send to client {address}: {e}")
                disconnected_clients.append(client)
        
        # Remove disconnected clients
        for client in disconnected_clients:
            if client in self.clients:
                self.clients.remove(client)
        
        return event
    
    @events.consumer(GlobalSignals.DISCONNECTED)
    def stop(self):
        """Stop the server"""
        broadcast(GlobalSignals.LOG, "🛑 Stopping Event Bridge Server...")
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
        if self.running:
            self.stop()

def main():
    """Main server entry point"""
    server = EventBridgeServer(port=8889)
    
    try:
        # Start server in a separate thread
        server.start()
        
        @events.consumer('user_action')
        def handle_user_action(action, user=None, **kwargs):
            broadcast(GlobalSignals.LOG, f"🎯 Server received user_action: {user} {action} (from {source})")
        
        @events.consumer('system_status')
        def handle_system_status(status, component=None, **kwargs):
            broadcast(GlobalSignals.LOG, f"📊 Server received system_status: {component} is {status} (from {source})")
        
        lock = threading.Lock()
        @events.consumer(GlobalSignals.LOG)
        def handle_log_message(message, **kwargs):
            with lock:
                # Print log messages with a prefix
                print(f"📜 {message}")

        # Generate some test events
        # def generate_test_events():
        #     time.sleep(2)  # Wait for server to start
        #     for i in range(3):
        #         broadcast('user_action', action='login', user=f'ServerUser{i}')
        #         time.sleep(2)
        #         broadcast('system_status', status='healthy', component=f'Service{i}')
        #         time.sleep(2)
        
        # test_thread = threading.Thread(target=generate_test_events, daemon=True)
        # test_thread.start()
        
        broadcast(GlobalSignals.LOG, "🔥 Event Bridge Server running. Press Ctrl+C to stop.")
        broadcast(GlobalSignals.LOG, "📡 Clients can connect and events will be synchronized.")
        
        # Keep the main thread alive
        while server.running:
            time.sleep(1)
            
    except KeyboardInterrupt:
        broadcast(GlobalSignals.LOG, "\n🛑 Shutting down server...")
        server.stop()

if __name__ == "__main__":
    main()
