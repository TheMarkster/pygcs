from __future__ import annotations

import re
from enum import StrEnum
from typing import Any, Dict, Set
import numpy as np
from functools import wraps

from ..event_bus import Broadcastable, consumer
from ..signals import GlobalSignals

_state_variables = set()

def grbl_state_var(func):
    """Decorator to register a function as a GRBL state variable"""
    _state_variables.add(func.__name__)
    return  property(func)

class State(StrEnum):
    IDLE = "Idle"
    RUN = "Run"
    ALARM = "Alarm"
    HOME = "Home"
    UNKNOWN = "Unknown"

    @staticmethod
    def decode(s: str) -> State:
        """Decode a string into an Idle state"""
        match s.lower():
            case "idle":
                return State.IDLE
            case "run":
                return State.RUN
            case "alarm":
                return State.ALARM
            case "home":
                return State.HOME
            case _:
                return State.UNKNOWN

class GRBLInfo(Broadcastable):
    def __init__(self):
        super().__init__()
        self.position: np.ndarray = np.array([0.0, 0.0, 0.0])
        self.last_update = ""
        self.probe_data = [0.0, 0.0, 0.0]
        self.runtime_variables: Set[str] = _state_variables.copy()
        self.data: Dict[str, Any] = {}

        self.state: State = State.UNKNOWN

    @property
    def is_idle(self) -> bool:
        """Check if the GRBL state is idle"""
        return self.state == State.IDLE

    @grbl_state_var
    def posx(self):
        return self.probe_data[0]

    @grbl_state_var
    def posy(self):
        return self.probe_data[1]

    @grbl_state_var
    def posz(self):
        return self.probe_data[2]

    def get_var(self, name: str):
        """Get a runtime variable by name"""
        if name in self.runtime_variables:
            return getattr(self, name)
        
        raise KeyError(f"Runtime variable '{name}' not found")
    
    @consumer(GlobalSignals.DATA_RECEIVED)
    def receive_message(self, message):
        if message.startswith('<') and message.endswith('>'):
            
            info = message[1:-1].split('|')
            new_state = State.decode(info[0])
            if new_state != self.state:
                self.state = new_state
                # print(f"State updated: {self.state}")

            for item in info[1:]:
                key, value = item.split(':')

                data = [float(v) for v in value.split(',')]
                self.data[key] = data
            # print(f"Runtime variables updated: {self.runtime_variables}")
        elif message.startswith('['):
            source, values, *rest = message[1:-1].split(':')
            if source == 'PRB':
                self.probe_data = [float(v) for v in values.split(',')]
                print(f"Probe data: {self.probe_data}")