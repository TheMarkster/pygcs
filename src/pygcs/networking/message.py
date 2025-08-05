from __future__ import annotations

from typing import Dict
import json
from dataclasses import dataclass

@dataclass
class Message:
    content: str
    data: Dict

    @staticmethod
    def deserialize(data: str) -> Message:
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
    def from_dict(data: dict) -> Message:
        return Message(
            content=data.get('content', ''),
            data=data.get('data', {})
        )