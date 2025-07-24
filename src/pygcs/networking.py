import struct
import json
from typing import Dict
from dataclasses import dataclass

@dataclass
class Message:
    content: str
    data: Dict

    @staticmethod
    def deserialize(data: str) -> 'Message':
        data = json.loads(data)
        return Message.from_dict(data)
    
    def serialize(self) -> str:
        return json.dumps(self.to_dict())
    
    def to_dict(self) -> dict:
        return {
            'content': self.content,
            'data': self.data
        }
    
    @staticmethod
    def from_dict(data: dict) -> 'Message':
        return Message(
            content=data.get('content', ''),
            data=data.get('data', {})
        )

def read_message(sock) -> Message:
    """Read a Message object from a socket"""
    data = read_block(sock)
    if not data:
        return None
    return Message.deserialize(data)

def write_message(sock, message: Message):
    """Send a Message object to a socket"""
    write_block(sock, message.serialize())

def read_block(sock):
    """Read a block of data prefixed by its size"""
    header = sock.recv(2)
    if not header:
        return None
    block_size = struct.unpack("!H", header)[0]
    if block_size == 0:
        return ""
    data = sock.recv(block_size)
    return data.decode('utf-8') if data else ""

def write_block(sock, data):
    """Send a block of data prefixed by its size"""
    if isinstance(data, str):
        message = data.encode('utf-8')
    else:
        message = json.dumps(data).encode('utf-8')
    block_size = struct.pack("!H", len(message))
    sock.sendall(block_size + message)