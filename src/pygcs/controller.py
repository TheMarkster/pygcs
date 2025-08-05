import threading
import serial
import time
import re
# from listeners import GRBLListener, TerminalListener
import json
from .signals import GlobalSignals
from .event_bus import events, Broadcastable, broadcast, consumer, local_broadcast
# from .logging import log as print

class SentCommand:
    def __init__(self, command: str):
        self.command = command
        self.start_timestamp = time.time()
        self.stop_timestamp = None
        self.elapsed_time = 0
        self.done = False
    
    def complete(self):
        if not self.done:
            self.stop_timestamp = time.time()
            self.elapsed_time = self.stop_timestamp - self.start_timestamp
            self.done = True
    
    def wait(self, timeout=10):
        if self.done:
            return
        start_time = time.time()
        while not self.done:
            if time.time() - start_time > timeout:
                raise TimeoutError(f"Command '{self.command}' timed out.")
            time.sleep(0.1)
        # print(f"Command {self.command} completed (blocking).")


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

def code_processor(name):
    """Decorator to register a code processor function"""
    def decorator(func):
        code_processors[name] = func
        return func
    return decorator

def get_code_processor(line):
    return code_processors.get(line, None)


class GRBLController(Broadcastable):
    def __init__(self):
        super().__init__()
        # print("Initializing GRBL Controller...")
        # Command management
        self.command_stack = []
        self.planner_queue = []
        self.error_stack = []
        self.max_command_stack_size = 10

        # Program state
        self.idle = False
        self.program_running = False
        self.current_program = ''
        self.state = dict(
            MPos = [0.0, 0.0, 0.0],
            Bf = [0,0],
            Fs = [0,0],
            Ov = [100,100,100],
        )
        
        # Predicted data
        self.target_position = [0, 0, 0]
        
        # Custom data
        self.custom_data = {}

        self.lock = threading.RLock()
        self.macro_path = './macros'
        
        self.paused = False
        self.last_probe = None

        self.wait_for_user = False

        self.program_queue = []

        self.running = True
        self.stopped = True
    
    def exec(self):
        self.stopped = False
        while self.running:
            ready = False
            with self.lock:
                if self.program_queue:
                    ready = True
                    self.program_running = True
                    func, *args = self.program_queue.pop(0)
            if ready:
                func(*args)
                with self.lock:
                    if len(self.program_queue) == 0:
                        self.program_running = False
            else:
                time.sleep(0.1)
        self.stopped = True
        print("Controller main loop exited.")
    

    @consumer(GlobalSignals.USER_RESPONSE)
    def user_response(self, response):
        self.wait_for_user = False

    def __del__(self):
        # Shutdown all connections and threads
        local_broadcast(GlobalSignals.DISCONNECTED, )

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

        tracker = self.send_command('?')
        
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
    
    def wait_for_idle(self, timeout=60):
        print("Waiting for machine to become idle...")
        start_time = time.time()
        while True:
            self.update_state(timeout=timeout)
            if self.idle:
                break
            
            if time.time() - start_time > timeout:
                raise TimeoutError("Timeout waiting for machine to become idle.")
            time.sleep(0.5)
        print("Machine is now idle.")

    def process_code(self, lines):
        trackers = []
        for line in lines:
            if line[0] == ';':
                continue

            line = re.sub(r'\s*\(.*?\)\s*', '', line).strip()

            for i, name in enumerate(['[posx]', '[posy]', '[posz]']):
                if name in line:
                    self.wait_for_probe(timeout=120)
                    print(f"Replaced {name} with {self.probe_data[i]:.3f} in line: {line}")
                    line = line.replace(name, f"{self.probe_data[i]:.3f}")

            if processor := get_code_processor(line):
                trackers.extend(processor())
            else:
                tracker = self.send_command(line)
                if tracker:
                    trackers.append(tracker)

        # if blocking:
        for tracker in trackers:
            if tracker:
                tracker.wait(timeout=600)
            
        time.sleep(0.5)
        self.wait_for_idle(timeout=120)

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

        self.process_code(lines)
        print("Macro execution complete.")

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
    
    @property
    def ser(self) -> serial.Serial:
        return self._ser

    @ser.setter
    def ser(self, value: serial.Serial):
        self._ser = value
    
    @consumer(GlobalSignals.DATA_RECEIVED)
    def receive_message(self, message):
        if message == 'ok':
            if self.command_stack:
                completed_command = self.command_stack.pop(0)
                completed_command.complete()
                print(f"Command completed: {completed_command.command} in {completed_command.elapsed_time:.2f} seconds")

                if self.planner_queue:
                    command, tracker = self.planner_queue.pop(0)
                    self.send_command(command, tracker=tracker)
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
                self.send_command(line, high_priority=True)

    def send_command(self, command, tracker=None, high_priority=False):
        command = command.strip()
        if not command:
            return None

        if command == 'exit':
            self.disconnect()
            return
        
        if tracker is None:
            tracker = SentCommand(command)
        
        with self.lock:
            if command.startswith('G38.2'):
                self.last_probe = tracker

            if len(self.command_stack) >= self.max_command_stack_size:
                print(f"Queuing command: {command}")
                if high_priority:
                    self.planner_queue.insert(0, (command, tracker))
                else:
                    self.planner_queue.append((command, tracker))
            else:
                print(f"Sending command: {command}")
                # self.ser.write((command + '\n').encode('utf-8'))
                broadcast(GlobalSignals.SEND_DATA, command + '\n')
                self.command_stack.append(tracker)
        
        return tracker
            
    def disconnect(self):
        if self.ser is None:
            return

        self.ser = None

    @code_processor('M0')
    def M0_process(self, line):
        trackers = []

        print("Pausing for user input...")
        # tracker.wait()
        time.sleep(0.5)
        self.wait_for_idle(timeout=120)

        with self.lock:
            self.paused = True
        tracker = self.send_command('M0')
        trackers.append(tracker)
        time.sleep(0.5)

        self.wait_for_user = True
        # broadcast.emit('prompt_user', "Press Enter to continue...")
        broadcast(GlobalSignals.PROMPT_USER, "Press Enter to continue...")
        while self.wait_for_user:
            time.sleep(0.1)
        
        tracker = self.send_command('~') # Cycle start

        with self.lock:
            self.paused = False

        trackers.append(tracker)

        return trackers

    # @staticmethod
    # def connect_remote(api: APIProcessor) -> GRBLController:
    #     # Check to see if object exists on the server
    #     obj_id = api.send_request('get_singleton', 'grbl_controller', timeout=5)

    #     controller = RemoteObject(api, obj_id, GRBLController)
    #     return controller

if __name__ == "__main__":
    pass