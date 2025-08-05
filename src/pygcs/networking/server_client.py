from __future__ import annotations

import socket
import threading
import json
from typing import Tuple
from .io import read_message, write_message
from .message import Message
from .processor import MessageProcessor

class NetworkObject:
    def __init__(self):
        self.connections: list[SocketConnection] = []
        self.processors: dict[str, list[MessageProcessor]] = {}

    def process_message(self, message: Message, sock: socket.socket, address: tuple):
        """Process incoming messages and forward to appropriate processor"""
        if message.content not in self.processors:
            print(f"❌ Unknown message type: {message.content}")
            return False
        
        for processor in self.processors[message.content]:
            processor.process_message(message, sock, address)

    def add_processor(self, processor: MessageProcessor):
        """Add a message processor for a specific content type"""
        proc_list = self.processors.setdefault(processor.content_type, [])
        proc_list.append(processor)
        processor.set_server(self)

    def register_connection(self, connection: SocketConnection):
        """Register a new connection"""
        if connection not in self.connections:
            self.connections.append(connection)

    def connection_closed(self, connection: SocketConnection):
        """Callback from SocketConnection when a connection is closed"""
        if connection in self.connections:
            self.connections.remove(connection)
    
    def send_message(self, message: Message, address=None):
        """Send a message to all registered connections"""
        for connection in self.connections:
            client_address = connection.address
            if address is not None and client_address != address:
                continue

            try:
                connection.send_message(message)
            except Exception as e:
                # print(f"❌ Failed to send message to {connection.address}: {e}")
                self.connection_closed(connection)
    
    def stop(self):
        """Stop all connections"""
        for connection in self.connections:
            connection.stop()
    
    def _cleanup(self):
        if self.connections:
            self.stop()
        

class SocketConnection(threading.Thread):
    def __init__(self, parent: NetworkObject, sock: socket.socket, address: Tuple, processors: dict[str, MessageProcessor]):
        super().__init__(daemon=True)
        self.parent: NetworkObject = parent
        self.sock: socket.socket = sock
        self.address: Tuple = address
        self.running: bool = False

    def run(self):
        """Start the thread to handle communication"""
        self.running = True
        self._receive_messages()

    def _receive_messages(self):
        """Handle communication with a connected client"""
        try:
            while self.running:
                try:
                    # Receive data from client
                    message = read_message(self.sock)  # Use self.sock, not undefined 'socket'
                    if message is None:  # Use 'is None' for explicit None check
                        # print(f"📡 Client {self.address} disconnected")
                        break

                    self.parent.process_message(message, self.sock, self.address)
                except socket.timeout:
                    continue
                except UnicodeDecodeError:
                    pass
                    print(f"❌ Client {self.address} sent invalid UTF-8 data - disconnecting")
                except json.JSONDecodeError:
                    pass
                    print(f"❌ Client {self.address} sent invalid JSON - disconnecting")
        except Exception as e:
            self.running = False
        finally:
            self._cleanup()  # Use the existing cleanup method
    
    def send_message(self, message: Message):
        """Send a message to a specific client socket"""
        try:
            write_message(self.sock, message)
        except Exception as e:
            # print(f"❌ Failed to send message to {self.address}: {e}")
            self._cleanup()  # Use the existing cleanup method
        
    def stop(self):
        """Stop the communicator"""
        if not self.running:
            return

        # print(f"🛑 Stopping socket thread for {self.address}...")
        self.running = False
        
        # Close socket
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
            self.sock = None
    
    def _cleanup(self):
        if self.running:
            self.stop()
                
        self.parent.connection_closed(self)

class Server(NetworkObject):
    def __init__(self, host='localhost', port=8888):
        super().__init__()
        self.host: str = host
        self.port: int = port
        self.running: bool = False

    def connect(self) -> bool:
        """Connect to the event bridge server"""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.settimeout(1)
            
            # Bind and listen
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)
            self.running = True
            
            # print(f"🌐 Event Bridge Server listening on {self.host}:{self.port}")
            
        except Exception as e:
            # print(f"❌ Error creating event bridge server: {e}")
            return False

        client_thread = threading.Thread(target=self._listen_for_client, daemon=True)
        client_thread.start()

        return True
    
    def _listen_for_client(self):
        """Listen for incoming connections and handle them"""
        try:
            while self.running:
                try:
                    client_socket, address = self.server_socket.accept()
                    # print(f"📡 Client connected from {address}")
                    
                    # Start a thread to handle this client
                    client_connection = SocketConnection(
                        parent=self,
                        sock=client_socket,
                        address=address,
                        processors=self.processors
                    )
                    self.register_connection(client_connection)
                    client_connection.start()
                except socket.timeout:
                    continue
        # except Exception as e:
            # print(f"❌ Error in server listener: {e}")
            # self.running = False
        except:
            self.running = False
        finally:
            self._cleanup()

    def stop(self):
        """Stop the server"""
        super().stop()

        if not self.running:
            return

        # print("🛑 Stopping Event Bridge Server...")
        self.running = False
        
        # Close server socket
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
    
    def _cleanup(self):
        """Clean up server resources"""
        super()._cleanup()

        if self.running:
            self.stop()

class Client(NetworkObject):
    def __init__(self, server_host='localhost', server_port=8888):
        super().__init__()
        self.server_host: str = server_host
        self.server_port: int = server_port

    @property
    def running(self) -> bool:
        return len(self.connections) > 0

    def connect(self) -> bool:
        """Connect to the event bridge server"""
        try:
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_socket.settimeout(1)
            server_socket.connect((self.server_host, self.server_port))
        except Exception as e:
            return False

        # Start a thread to handle communication with the server
        server_connection = SocketConnection(self, server_socket, (self.server_host, self.server_port), self.processors)
        self.register_connection(server_connection)
        server_connection.start()

        return True
