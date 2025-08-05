from __future__ import annotations

from .message import Message
import socket
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .server_client import NetworkObject

class MessageProcessor:
    def __init__(self, content_type):
        self.content_type = content_type
        self.server: NetworkObject = None

    def set_server(self, server: NetworkObject):
        """Set the server instance for this processor"""
        if self.server is None:
            self.server = server
        else:
            raise RuntimeError("Server is already set for this processor")

    def process_message(self, message: Message, sock: socket.socket, address: tuple) -> bool:
        if message.content != self.content_type:
            return False
    
    def send_message(self, message: Message, address: tuple = None):
        """Send a message to the server's connections"""
        if self.server is None:
            raise RuntimeError("Server is not set for this processor")
        
        self.server.send_message(message, address)
