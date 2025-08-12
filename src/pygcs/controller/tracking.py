from __future__ import annotations

import time
from enum import StrEnum
from typing import TYPE_CHECKING, Dict
import re

if TYPE_CHECKING:
    from .state import GRBLInfo


class CommandStage(StrEnum):
    PLANNING = "planning"
    SUBMITTED = "submitted"
    ERROR = "error"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    STAGING = "staging"

class CommandTracker:
    def __init__(self, grbl_info: GRBLInfo, command: str, info: Dict = None, callback: callable = None):
        self.grbl_info: GRBLInfo = grbl_info
        self._command: str = command

        self.info: Dict = info or {}

        self.callback: callable = callback
        self.runtime_var: bool = re.match(r'^.+\[.+\].*$', command) is not None

        self.start_timestamp: float = None
        self.stop_timestamp: float = None
        self.elapsed_time: float = 0
        
        self.result: str = None
        self.error_message: str = None
        self.stage: CommandStage = CommandStage.STAGING

    @property
    def done(self) -> bool:
        """Check if the command is done (either completed or cancelled)"""
        return self.stage in (CommandStage.COMPLETED, CommandStage.CANCELLED, CommandStage.ERROR)
    
    @property
    def command(self) -> str:
        """Return the command string, updating runtime variables if needed"""
        if self.runtime_var:
            command = self._command
            runtime_variables = re.findall(r'\[([^\]]+)\]', command)
            command = re.sub(r'\[([^\]]+)\]', '{}', self._command)  # Remove runtime variables from command
            values = []
            for var in runtime_variables:
                values.append(str(self.grbl_info.get_var(var)))
            return command.format(*values)
        else:
            return self._command

    def planning(self):
        """Mark this command as being in the planning stage"""
        if self.stage != CommandStage.STAGING:
            raise RuntimeError("Cannot plan command that is not in preplanning stage.")

        self.stage = CommandStage.PLANNING

    def staging(self):
        """Mark this command as being in the staging stage"""
        if self.stage != CommandStage.PLANNING:
            raise RuntimeError("Cannot be placed back in staging after submission.")

        self.stage = CommandStage.STAGING
    
    @property
    def in_planning(self) -> bool:
        """Check if the command is in the planning stage"""
        return self.stage == CommandStage.PLANNING
    
    @property
    def in_staging(self) -> bool:
        """Check if the command is in the staging stage"""
        return self.stage == CommandStage.STAGING
    
    @property
    def is_submitted(self) -> bool:        
        """Check if the command has been submitted"""
        return self.stage == CommandStage.SUBMITTED
    
    @property
    def cancelled(self) -> bool:
        """Check if the command has been cancelled"""
        return self.stage == CommandStage.CANCELLED
    
    @property
    def errored(self) -> bool:
        """Check if the command has encountered an error"""
        return self.stage == CommandStage.ERROR
    
    @property
    def completed(self) -> bool:
        """Check if the command has been completed successfully"""
        return self.stage == CommandStage.COMPLETED

    def complete(self):
        """Mark the command as completed"""
        if self.stage != CommandStage.SUBMITTED:
            raise RuntimeError("Cannot complete command that is not submitted.")

        self.stop_timestamp = time.time()
        if self.start_timestamp:
            self.elapsed_time = self.stop_timestamp - self.start_timestamp
        self.stage = CommandStage.COMPLETED

        if self.callback:
            self.callback(self)
    
    def cancel(self):
        """Cancel the command, marking it as done without completion"""
        if self.stage != CommandStage.PLANNING:
            raise RuntimeError("Cannot cancel command that is not in planning stage.")
        
        self.stop_timestamp = time.time()
        if self.start_timestamp:
            self.elapsed_time = self.stop_timestamp - self.start_timestamp
        self.stage = CommandStage.CANCELLED
        
        if self.callback:
            self.callback(self)
    
    def wait(self, timeout=None):
        if self.stage in (CommandStage.COMPLETED, CommandStage.CANCELLED, CommandStage.ERROR):
            return
        
        start_time = time.time()
        while self.stage not in (CommandStage.COMPLETED, CommandStage.CANCELLED, CommandStage.ERROR):
            if timeout:
                if time.time() - start_time > timeout:
                    raise TimeoutError(f"Command '{self.command}' timed out.")
            time.sleep(0.1)
    
    def submit(self):
        """Submit the command to the controller"""
        if self.stage != CommandStage.PLANNING and self.stage != CommandStage.STAGING:
            raise RuntimeError("Cannot submit command that is not in planning stage.")

        self.stage = CommandStage.SUBMITTED
        self.start_timestamp = time.time()
    
    def set_result(self, result: str):
        """Set the result of the command execution"""
        self.result = result
    
    def error(self, error_message: str):
        """Set an error message for the command"""
        self.stage = CommandStage.ERROR
        self.error_message = error_message
