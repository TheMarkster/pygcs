from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Dict, Any

def broadcast_func(func):
    func._broadcast_func = True
    return func

_metastate = {}

def get_metastate() -> Dict[str, Any]:
    return _metastate

@dataclass
class Event:
    signal: str
    args: tuple
    kwargs: dict
    _metadata: dict

    def __post_init__(self):
        for k, v in get_metastate().items():
            if k not in self._metadata:
                self._metadata[k] = v
        # self.record_origin()

    def to_dict(self) -> dict:
        return {
            'signal': self.signal,
            'args': self.args,
            'kwargs': self.kwargs,
            '_metadata': self._metadata
        }

    @staticmethod
    def from_dict(data: dict) -> Event:
        return Event(
            signal=data.get('signal', ''),
            args=tuple(data.get('args', ())),
            kwargs=data.get('kwargs', {}),
            _metadata=data.get('_metadata', {})
        )

    def serialize(self) -> str:
        return json.dumps(self.to_dict())

    @staticmethod
    def deserialize(data: str) -> Event:
        data = json.loads(data)
        return Event.from_dict(data)
    
    def get_path_data(self):
        devices = self._metadata.setdefault('device', [])
        if len(devices) == 0:
            devices.append('localhost')
        path = self._metadata.setdefault('path', [])
        if len(path) == 0:
            path.append([])

        return devices, path

    def get_local_path(self):
        devices, path = self.get_path_data()
        return path[-1]

    def push_path(self, host: str):
        # Local host data pushed back as we enter new network
        devices, path = self.get_path_data()

        devices.insert(-1, host)  # Insert before 'localhost'
        path.insert(-1, path[-1].copy())  # Duplicate current local path segment
        path[-1].clear()
