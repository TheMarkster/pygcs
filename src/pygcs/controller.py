from __future__ import annotations

from dataclasses import dataclass
from functools import wraps
import threading
from typing import List, Dict
import numpy as np
import serial
import time
import re
# from listeners import GRBLListener, TerminalListener
import json
from .signals import GlobalSignals
from .event_bus import events, Broadcastable, broadcast, consumer, local_broadcas
from .gcode_prcessing import get_gcode_processor
# from .logging import log as print

class CommandTracker:
    def __init__(self, parent: GRBLController, command: str, info: Dict = None, callback: callable = None):
        self.parent: GRBLController = parent
        self.command: str = command
        self.start_timestamp: float = None
        self.stop_timestamp: float = None
        self.elapsed_time: float = 0
        self.done: bool = False
        self.cancelled: bool = False
        self.in_planning: bool = False
        self.submitted: bool = False
        self.info: Dict = info or {}
        self.callback: callable = callback
        self.runtime_var: bool = re.match(r'\[.*\]', command) is not None

    def planning(self):
        """Mark this command as being in the planning stage"""
        self.in_planning = True

    def complete(self):
        if not self.done and not self.cancelled:
            self.stop_timestamp = time.time()
            self.elapsed_time = self.stop_timestamp - self.start_timestamp
            self.done = True

            if self.callback:
                self.callback(self)
    
    def cancel(self):
        """Cancel the command, marking it as done without completion"""
        if not self.done and not self.cancelled:
            self.cancelled = True
            if self.start_timestamp:
                self.stop_timestamp = time.time()
            self.elapsed_time = self.stop_timestamp - self.start_timestamp
            self.cancelled = True

            if self.callback:
                self.callback(self)
    
    def wait(self, timeout=None):
        if self.done or self.cancelled:
            return
        
        start_time = time.time()
        while not self.done and not self.cancelled:
            if time.time() - start_time > timeout:
                raise TimeoutError(f"Command '{self.command}' timed out.")
            time.sleep(0.1)
    
    def presubmit(self):
        """Pre-submit processing, can be overridden by subclasses"""
        if self.runtime_var:
            self.command = self.parent.state.update_runtime_vars(self.command)

    def submit(self):
        """Submit the command to the controller"""
        self.in_planning = False
        self.submitted = True
        self.start_timestamp = time.time()


class ErrorState:
    def __init__(self):
        self.error_codes = []
        self.timestamps = []
    
    def get_state(self):
        return self.error_codes, self.timestamps
    
    def error_occurred(self, code):
        self.error_codes.append(code)
        self.timestamps.append(time.time())
    
    def clear_errors(self):
        self.error_codes.clear()
        self.timestamps.clear()


#<Idle|MPos:-601.500,-601.500,-4.000|Bf:14.000,127.000|Fs:0.000,0.000|Ov:100.000,100.000,100.000|FS:0.000,0.000|WCO:-104.860,-143.940,-129.917>
class PositionState:
    def __init__(self):
        self.position = [0.0, 0.0, 0.0]
        self.feed_rate = 0.0
        self.spindle_speed = 0.0
    
    def update_position(self, pos):
        self.position = pos
    
    def update_feed_rate(self, rate):
        self.feed_rate = rate
    
    def update_spindle_speed(self, speed):
        self.spindle_speed = speed
    
    def serialize(self):
        return {
            "position": self.position,
            "feed_rate": self.feed_rate,
            "spindle_speed": self.spindle_speed
        }

    def deserialize(self, state_str):
        state = json.loads(state_str)
        self.position = state.get("position", [0.0, 0.0, 0.0])
        self.feed_rate = state.get("feed_rate", 0.0)
        self.spindle_speed = state.get("spindle_speed", 0.0)

code_processors = {}

def code_replacement(code):
    """Decorator to register code replacement processors"""
    def decorator(func):
        @wraps(func)
        def inner(*args, **kwargs):
            return func(*args, **kwargs)
        inner._code_replacement = True
        inner._code_name = code
        return inner
    return decorator

def custom_command(name):
    """Decorator to register a custom command"""
    def decorator(func):
        @wraps(func)
        def inner(*args, **kwargs):
            return func(*args, **kwargs)
        inner._custom_command = True
        inner._code_name = name
        return inner
    return decorator

def get_code_processor(line):
    return code_processors.get(line, None)

def grbl_state_var(name):
    def decorator(func):
        """Decorator to register a function as a GRBL state variable"""
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            return func(self, *args, **kwargs)
        wrapper._grbl_state_var = True
        wrapper._grbl_state_var_name = name
        return wrapper
    return decorator

class GRBLState(Broadcastable):
    def __init__(self):
        super().__init__()
        self.idle = False
        self.position: np.ndarray = np.array([0.0, 0.0, 0.0])
        self.error_state = ErrorState()
        self.last_update = ""
        self.probe_data = [0.0, 0.0, 0.0]
        self.runtime_variables: Dict[str, callable] = {}

        # Discover state variables
        for attr_name in dir(self):
            attr = getattr(self, attr_name)

            if callable(attr) and hasattr(attr, '_grbl_state_var'):
                # Register the method as a GRBL state variable
                var_name = attr._grbl_state_var_name
                self.runtime_variables[var_name] = attr

    @grbl_state_var
    def posx(self):
        return self.position[0]

    @grbl_state_var
    def posy(self):
        return self.position[1]

    @grbl_state_var
    def posz(self):
        return self.position[2]

    def update_runtime_vars(self, command: str) -> str:
        """Update runtime variables in the command string"""
        runtime_variables = re.findall(r'\[([^\]]+)\]', command)
        command = re.sub(r'\[([^\]]+)\]', '%s', command)  # Remove runtime variables from command
        values = []
        for var in runtime_variables:
            if var in self.runtime_variables:
                values.append(str(self.runtime_variables[var]()))
            else:
                raise ValueError(f"Runtime variable '{var}' not found in GRBL state.")
        return command.format(*values)


class Program:
    def __init__(self, parent: GRBLController, lines: List[str], name=None, program_type=None):
        self.parent: GRBLController = parent
        self.name: str = name or "Unnamed Program"
        self.type: str = program_type or "Program"
        self.lines: List[str] = lines
        self.estimated_time: List[float] = None
        self.trackers: List[CommandTracker] = None
        self.cur_line: int = 0
        self.running: bool = False

        # Apply all processing upfront
        self.pre_process()
        self.estimate_time()
        self.create_trackers()
    
    def create_trackers(self):
        """Create command trackers for each line in the program"""
        self.trackers = [CommandTracker(self.parent, command, info={'program': self.name, 'line_index': i}) for i, command in enumerate(self.lines)]

    def estimate_time(self):
        """Estimate the time it will take to run the program"""
        self.estimated_time = 0

    def pre_process(self):
        gcode_processor = get_gcode_processor()
        gcode_processor.reset()
        for line in self.lines:
            gcode_processor.process_line(line)
        self.lines = gcode_processor.get_lines()

    def command_callback(self, command: CommandTracker):
        if command.done:
            self.cur_line = command.info.get('line_index', self.cur_line+1)

        if command.cancelled:
            pass


class GRBLController(Broadcastable):
    def __init__(self):
        super().__init__()

        # Settings
        self.max_command_queue_size = 10
        self.status_query_frequency = 5

        # Command management
        self.command_queue: List[CommandTracker] = []
        self.planner_queue: List[str] = []
        self.current_program: Program = None

        # Program state
        self._state: GRBLState = GRBLState()
        self.update_frequency: float = 10.0

        self.lock: threading.RLock = threading.RLock()
        self.macro_path = './macros'
        self.running: bool = False
        self.last_probe: CommandTracker = None

    def exec(self):
        """Main loop for the controller"""
        self.stopped = False
        self.running = True
        while self.running:
            thread = threading.Thread(target=self._continuous_updates, daemon=True)
            thread.start()

            if self.paused:
                time.sleep(0.1)
                continue

            if len(self.command_queue) < self.max_command_queue_size:
                if self.planner_queue:
                    tracker = self.planner_queue.pop(0)
                    
                    if tracker.command[0] == '%':
                        command_name = tracker.command[1:]
                        self.exec_custom_command(command_name, tracker)
                    else:
                        tracker.presubmit()
                        self.send_command(tracker.command, tracker)
        self.stopped = True
        print("Controller main loop exited.")
    
    def execute_custom_command(self, command_name: str, tracker: CommandTracker):
        """Execute a custom command by name"""
        if command_name in self.custom_commands:
            func = self.custom_commands[command_name]
            func() # TODO: Add parameters to custom commands
            tracker.complete()
        else:
            print(f"Custom command '{command_name}' not found.")
            tracker.cancel()

    # Command helpers
    def resume_program(self):
        self.queue_command('~', immediate=True)

    # @consumer(GlobalSignals.USER_RESPONSE)
    # def user_response(self, response):
    #     self.wait_for_user = False

    # def __del__(self):
    #     # Shutdown all connections and threads
    #     local_broadcast(GlobalSignals.DISCONNECTED, )

    @consumer(GlobalSignals.DISCONNECTED)
    def shutdown(self):
        self.running = False

    def wait_for_probe(self, timeout=60):
        if self.last_probe:
            self.last_probe.wait(timeout=timeout)
            self.last_probe = None

    def update_state(self, timeout=1):
        paused = False
        with self.lock:
            paused = self.paused
        
        if paused:
            self.wait_for_unpause()

        tracker = self.queue_command('?')
        
        tracker.wait(timeout=timeout)
        idle, *others = self.last_update.split('|')
        self.last_update = ""
        self.idle = idle == 'Idle'

        def extract_numbers(value):
            try:
                numbers = [float(num) for num in value.split(',')]
                return numbers if numbers else None
            except ValueError:
                return None

        for arg in others:
            key, value = arg.split(':')
            
            if result := extract_numbers(value):
                self.state[key] = result
                continue

            self.state[key] = value
    @custom_command('wait_for_idle')
    def wait_for_idle(self, timeout=60):
        print("Waiting for machine to become idle...")
        start_time = time.time()
        while True:
            if time.time() - start_time > timeout:
                raise TimeoutError("Timeout waiting for machine to become idle.")

            if len(self.command_queue) > 0:
                time.sleep(0.5)
                continue

            if not self.check_idle():
                time.sleep(0.1)
                continue
            
            break
        print("Machine is now idle.")

    # @consumer(GlobalSignals.EXEC_MACRO)
    def exec_macro(self, command, main_thread=False):
        if not main_thread:
            with self.lock:
                if self.program_running:
                    print("ERROR:" + "Cannot execute macro while another is running.")
                else:
                    self.program_queue.append((self.exec_macro, command, True))
            return

        path = f"{self.macro_path}/{command}.g"

        with open(path, 'r') as file:
            lines = file.readlines()

        program = Program(self, lines, name=f"macro_{command}", program_type="Macro")
        for line, tracker in zip(program.lines, program.trackers):
            self.queue_command(line, tracker=tracker)

        return program
    
    def _continuous_updates(self):
        """Continuously update the controller state at a given frequency"""
        while self.running:
            start = time.time()
            tracker = self.queue_command('?')
            tracker.wait()
            elapsed = time.time() - start
            time.sleep(max(0, 1/self.update_frequency - elapsed))

    def wait_for_unpause(self, timeout=1000):
        print("Waiting for unpause...")
        start_time = time.time()
        while True:
            with self.lock:
                if not self.paused:
                    break
            
            if time.time() - start_time > timeout:
                raise TimeoutError("Timeout waiting for unpause.")
            time.sleep(0.5)
        print("Unpaused.")
    
    def get_error_state(self):
        codes = []
        for error_code, timestamp in self.error_stack:
            codes.append(error_code)
        
        return codes
    
    def clear_errors(self):
        self.error_stack.clear()

    @consumer(GlobalSignals.DATA_RECEIVED)
    def receive_message(self, message):
        if message == 'ok':
            if self.command_queue:
                completed_command = self.command_queue.pop(0)
                completed_command.complete()
                print(f"Command completed: {completed_command.command} in {completed_command.elapsed_time:.2f} seconds")

                # if self.planner_queue:
                #     command, tracker = self.planner_queue.pop(0)
                #     self.send_command(command, tracker=tracker)
            else:
                print("Received 'ok' but command stack is empty.")
        elif message.startswith('error'):
            _, error_code = message.split(':')
            error_code = int(error_code)
            self.error_stack.append((error_code, time.time()))
        elif message.startswith('<') and message.endswith('>'):
            self.last_update = message[1:-1]
            print(f"Status update: {message}")
            
            # Broadcast status update to connected clients
            if hasattr(self, 'control_server'):
                self.control_server.broadcast_event("status_update", {
                    "raw_message": message,
                    "state": self.state
                })
        elif message.startswith('['):
            source, values, *rest = message[1:-1].split(':')
            if source == 'PRB':
                self.probe_data = [float(v) for v in values.split(',')]
                print(f"Probe data: {self.probe_data}")
        else:
            print(f"Received message: {message}")
    
    @consumer(GlobalSignals.LOAD_PROGRAM)
    def load_program(self, program):
        if self.program_running:
            print("ERROR:" + "Cannot load program while another is running.")

        self.program = program
    
    @consumer(GlobalSignals.PROGRAM_START)
    def program_start(self):
        for line in self.program.splitlines():
            line = line.strip()
            if line and not line.startswith(';'):
                self.queue_command(line, high_priority=True)

    def queue_command(self, command, immediate=False, tracker=None, high_priority=False):
        command = command.strip()
        if not command:
            return None

        if command == 'exit':
            self.disconnect()
            return
        
        if tracker is None:
            tracker = CommandTracker(command)
        
        with self.lock:
            if immediate:
                self.send_command(command, tracker)
                return tracker
            
            print(f"Queuing command: {command}")
            if high_priority:
                self.planner_queue.insert(0, (command, tracker))
            else:
                self.planner_queue.append((command, tracker))
        
        return tracker
    
    def send_command(self, command: str, tracker: CommandTracker = None):
        """Send a command to the GRBL controller"""
        print(f"Sending command: {command}")
        if command.startswith('G38.2'):
            self.last_probe = tracker
        broadcast(GlobalSignals.SEND_DATA, command + '\n')
        self.command_queue.append(tracker)
    
    def check_idle(self):
        """Check if the controller is idle"""
        with self.lock:
            return len(self.command_queue) == 0 and len(self.planner_queue) == 0 and self._state.idle

    def wait(self):
        """Waits for command stack to be empty and machine to be idle"""
        while not self.check_idle():
            time.sleep(0.1)

    # @staticmethod
    # def connect_remote(api: APIProcessor) -> GRBLController:
    #     # Check to see if object exists on the server
    #     obj_id = api.send_request('get_singleton', 'grbl_controller', timeout=5)

    #     controller = RemoteObject(api, obj_id, GRBLController)
    #     return controller

if __name__ == "__main__":
    pass