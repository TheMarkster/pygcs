from __future__ import annotations

from functools import wraps
import threading
from typing import List, Dict
import time

from ..signals import GlobalSignals
from ..event_bus import events, Broadcastable, broadcast, consumer, local_broadcast
from .gcode_prcessing import get_gcode_processor

from .state import GRBLInfo
from .tracking import CommandTracker
from .program import Program


def custom_command(name):
    """Decorator to register a custom command"""
    def decorator(func):
        @wraps(func)
        def inner(*args, **kwargs):
            return func(*args, **kwargs)
        inner._custom_command = True
        inner._command_name = name
        return inner
    return decorator

class GRBLController(Broadcastable):
    def __init__(self):
        super().__init__()

        self.processor = get_gcode_processor()

        # Settings
        self.max_command_queue_size = 10
        self.status_query_frequency = 5

        # Command management
        self.command_queue: List[CommandTracker] = []
        self.planner_queue: List[CommandTracker] = []
        self.command_history: List[CommandTracker] = []
        self.current_program: Program = None
        self.custom_commands: Dict[str, callable] = {}

        # Program state
        self._info: GRBLInfo = GRBLInfo()
        self.update_frequency: float = 10.0
        self.paused = False
        self.program_running = False
        self.program: Program = None

        self.lock: threading.RLock = threading.RLock()
        self.macro_path = './macros'
        self.running: bool = False
        self.last_probe: CommandTracker = None

        # Discover custom commands
        for attr_name in dir(self):
            attr = getattr(self, attr_name)

            if not callable(attr):
                continue

            if hasattr(attr, '_custom_command'):
                command_name = attr._command_name
                self.custom_commands[command_name] = attr

    def exec(self):
        """Main loop for the controller"""
        self.stopped = False
        self.running = True
        thread = threading.Thread(target=self._continuous_updates, daemon=True)
        thread.start()
        while self.running:
            if self.paused:
                time.sleep(0.1)
                continue

            if self.program_running and not self.program.queued:
                for tracker in self.program.trackers:
                    if tracker.in_staging:
                        self.planner_queue.append(tracker)
                        tracker.planning()
                self.program.queued = True

            if not self.program_running and self.program and self.program.queued:
                for tracker in self.program.trackers:
                    if tracker.in_planning:
                        self.planner_queue.remove(tracker)
                        tracker.staging()
                self.program.queued = False

            if len(self.command_queue) < self.max_command_queue_size:
                if self.planner_queue:
                    tracker = self.planner_queue.pop(0)
                    self.send_command(tracker)
            
            time.sleep(0.1)
        self.stopped = True
        print("Controller main loop exited.")
    
    def execute_custom_command(self, tracker: CommandTracker):
        """Execute a custom command by name"""
        command_name = tracker.command[1:]
        if command_name in self.custom_commands:
            func = self.custom_commands[command_name]
            func() # TODO: Add parameters to custom commands
        else:
            raise Exception(f"Custom command '{command_name}' not found.")
    
    def home(self):
        attempts = 3
        while attempts > 0:
            tracker = self.queue_command('$H')
            tracker.wait(timeout=60)
            if tracker.errored:
                print("Errors detected:", tracker.error_message)
                self.queue_command('$X', immediate=True)
                time.sleep(0.5)
                attempts -= 1
            else:
                print("Homing successful")
                break

    @consumer(GlobalSignals.DISCONNECTED)
    def shutdown(self):
        self.running = False

    @custom_command('wait_for_idle')
    def wait_for_idle(self, timeout=60):
        print("Waiting for machine to become idle...")
        time.sleep(0.5)
        start_time = time.time()
        while True:
            if time.time() - start_time > timeout:
                raise TimeoutError("Timeout waiting for machine to become idle.")

            if len(self.command_queue) > 0:
                time.sleep(0.5)
                continue

            if not self._info.is_idle:
                time.sleep(0.1)
                continue
            
            break
        print("Machine is now idle.")

    @custom_command('wait_for_last_command')
    def wait_for_last_command(self, timeout=60):
        """Wait for the last command to complete"""
        if not self.command_history:
            print("No commands in queue.")
            return
        else:
            print(f"Waiting for command '{self.command_history[-1].command}' to complete...")
            self.command_history[-1].wait()

    # @consumer(GlobalSignals.EXEC_MACRO)
    def exec_macro(self, command):
        path = f"{self.macro_path}/{command}.g"

        with open(path, 'r') as file:
            lines = file.readlines()

        program = Program(self.processor, self._info, lines, name=f"macro_{command}", program_type="Macro")
        # for line, tracker in zip(program.lines, program.trackers):
        #     self.queue_command(line, tracker=tracker)
        for tracker in program.trackers:
            self.planner_queue.append(tracker)
            tracker.planning()

        return program
    
    def _continuous_updates(self):
        """Continuously update the controller state at a given frequency"""
        while self.running:
            start = time.time()
            tracker = self.queue_command('?', immediate=True)
            tracker.wait()
            elapsed = time.time() - start
            time.sleep(max(0, 1/self.update_frequency - elapsed))

    @consumer(GlobalSignals.DATA_RECEIVED)
    def receive_message(self, message):
        if message == 'ok':
            if self.command_queue:
                completed_command = self.command_queue.pop(0)
                completed_command.complete()
                print(f"Command completed: {completed_command.command} in {completed_command.elapsed_time:.2f} seconds")
            else:
                print("Received 'ok' but command stack is empty.")
        elif message.startswith('error'):
            _, error_code = message.split(':')
            error_code = int(error_code.strip())

            completed_command = self.command_queue.pop(0) if self.command_queue else None
            completed_command.error(error_code)

            print(f"Command failed with error: {completed_command.command} with error code {error_code}")
        else:
            # print(f"Received message: {message}")
            pass
    
    @consumer(GlobalSignals.LOAD_PROGRAM)
    def load_program(self, program: str) -> Program:
        if self.program_running:
            print("ERROR:" + "Cannot load program while another is running.")
        
        if isinstance(program, str):
            lines = program.splitlines()
        elif isinstance(program, list):
            lines = program
        else:
            raise TypeError("Program must be a string or a list of strings.")

        program = Program(self.processor, self._info, lines)
        self.program = program

        return program
    
    @consumer(GlobalSignals.PROGRAM_START)
    def program_start(self):
        self.program_running = True
    
    @consumer(GlobalSignals.PROGRAM_STOP)
    def program_stop(self):
        """Stop the current program"""
        self.program_running = False

    @consumer("queue_immediate")
    def queue_immediate(self, command: str):
        self.queue_command(command, immediate=True)

    def queue_command(self, command, immediate=False, tracker=None, high_priority=False):
        command = command.strip()
        if not command:
            return None

        if command == 'exit':
            self.disconnect()
            return
        
        if tracker is None:
            tracker = CommandTracker(self, command)
        
        with self.lock:
            if immediate:
                self.send_command(tracker)
                return tracker
            
            # print(f"Queuing command: {command}")
            if high_priority:
                self.planner_queue.insert(0, tracker)
            else:
                self.planner_queue.append(tracker)
        
        return tracker
    
    def send_command(self, tracker: CommandTracker = None):
        """Send a command to the GRBL controller"""
        # print(f"Sending command: {command}")
        # if command.startswith('G38.2'):
        #     self.last_probe = tracker
        if tracker.command[0] == '%':
            tracker.submit()
            try:
                self.execute_custom_command(tracker)
                tracker.complete()
            except Exception as e:
                tracker.error(str(e))
        else:
            broadcast(GlobalSignals.SEND_DATA, tracker.command + '\n')
            tracker.submit()
            self.command_queue.append(tracker)

        self.command_history.append(tracker)
    
    def check_idle(self):
        """Check if the controller is idle"""
        with self.lock:
            # TODO: Check if commands in queue are motion commands
            return len(self.command_queue) == 0 and self._info.is_idle

    def wait(self):
        """Waits for command stack to be empty and machine to be idle"""
        while not self.check_idle():
            time.sleep(0.1)

