from .message import Message
import socket
import json
import struct

def _recv_exact(sock: socket.socket, num_bytes: int) -> bytes:
    """Receive exactly num_bytes from socket, handling partial reads"""
    data = b''
    while len(data) < num_bytes:
        chunk = sock.recv(num_bytes - len(data))
        if not chunk:  # Connection closed
            return b''
        data += chunk
    return data

def read_message(sock) -> Message:
    """Read a Message object from a socket"""
    data = read_block(sock)
    
    if not data:
        return None
    
    return Message.deserialize(data)

def write_message(sock: socket.socket, message: Message):
    """Send a Message object to a socket"""
    write_block(sock, message.serialize())

def read_block(sock: socket.socket) -> str:
    """Read a block of data prefixed by its size"""
    header = _recv_exact(sock, 2)  # Read exactly 2 bytes for block size
    if not header:
        return None
    
    block_size = struct.unpack("!H", header)[0]
    if block_size == 0:
        return ""
    
    data = _recv_exact(sock, block_size)
    if not data:
        return None

    return data.decode('utf-8')

def write_block(sock: socket.socket, data: str | dict) -> None:
    """Send a block of data prefixed by its size"""
    if isinstance(data, str):
        message = data.encode('utf-8')
    else:
        message = json.dumps(data).encode('utf-8')
    block_size = struct.pack("!H", len(message))
    sock.sendall(block_size + message)

