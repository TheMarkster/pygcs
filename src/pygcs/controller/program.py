from typing import List, Dict
from .tracking import CommandTracker
from .gcode_prcessing import GCodeProcessor
from .state import GRBLInfo


class Program:
    def __init__(self, processor: GCodeProcessor, info: GRBLInfo, lines: List[str], name=None, program_type=None):
        self.processor: GCodeProcessor = processor
        self.info: GRBLInfo = info
        self.name: str = name or "Unnamed Program"
        self.type: str = program_type or "Program"
        self.lines: List[str] = lines
        self.estimated_time: List[float] = None
        self.trackers: List[CommandTracker] = None
        self.cur_line: int = 0
        self.running: bool = False
        self.queued: bool = False

        # Apply all processing upfront
        self.pre_process()
        self.estimate_time()
        self.create_trackers()
    
    def wait(self, timeout=None):
        """Wait for the program to finish executing"""
        for tracker in self.trackers:
            tracker.wait()
    
    def create_trackers(self):
        """Create command trackers for each line in the program"""
        self.trackers = [CommandTracker(self.info, command, info={'program': self.name, 'line_index': i}) for i, command in enumerate(self.lines)]

    def estimate_time(self):
        """Estimate the time it will take to run the program"""
        self.estimated_time = 0

    def pre_process(self):
        self.processor.reset()
        self.processor.process_lines(self.lines)
        # for line in self.lines:
        #     gcode_processor.process_line(line)
        self.lines = self.processor.get_lines()
        pass

    def command_callback(self, command: CommandTracker):
        if command.done:
            self.cur_line = command.info.get('line_index', self.cur_line+1)

        if command.cancelled:
            pass