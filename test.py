from __future__ import annotations

import serial
import serial.tools.list_ports as list_ports
import time
import threading
import sys
import re

# ports = list_ports.comports()
# for p in ports:
#     print(p)

def check_connection(func):
    def wrapper(self, *args, **kwargs):
        if self.ser is None:
            raise ConnectionError("Not connected to GRBL device.")
        return func(self, *args, **kwargs)
    return wrapper

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

class TerminalListener(threading.Thread):
    def __init__(self, controller: GRBLController):
        super().__init__()
        self.controller = controller
        self.running = True
    
    @property
    def ser(self) -> serial.Serial:
        return self.controller.ser

    @property
    def controller(self) -> GRBLController:
        return self._controller
    
    @controller.setter
    def controller(self, value: GRBLController):
        self._controller = value
    
    def run(self):
        while self.running:
            try:
                line = sys.stdin.readline().rstrip()
                print(f"\r> {line}")
                controller.send_command(line)
            except:
                pass

    def stop(self):
        self.running = False

class GRBLListener(threading.Thread):
    def __init__(self, controller: GRBLController):
        super().__init__()
        self.controller = controller
        self.running = True
    
    @property
    def ser(self) -> serial.Serial:
        return self.controller.ser

    def run(self):
        while self.running:
            try:
                line = self.ser.readline().decode('utf-8').rstrip()
                if line:
                    self.controller.receive_message(line)
            except:
                pass

    def stop(self):
        self.running = False

class GRBLController:
    def __init__(self, port, baudrate=115200, timeout=1):
        print("Initializing GRBL Controller...")
        self.command_stack = []
        self.planner_queue = []
        self.error_stack = []
        self.max_command_stack_size = 10
        self.ser = serial.Serial(port, baudrate, timeout=timeout)
        print(f"Connected to {port} at {baudrate} baud.")
        self.lock = threading.Lock()
        self.monitor_thread = GRBLListener(self)
        self.monitor_thread.start()
        self.terminal_thread = TerminalListener(self)
        self.terminal_thread.start()
        self.macro_path = './macros'
        self.last_update = ""
        self.paused = False
        self.last_probe = None
        self.state = dict(
            MPos = [0.0, 0.0, 0.0],
            Bf = [0,0],
            Fs = [0,0],
            Ov = [100,100,100],
        )
    
    @property
    def x(self):
        return self.state['MPos'][0]

    @property
    def y(self):
        return self.state['MPos'][1]
    
    @property
    def z(self):
        return self.state['MPos'][2]

    @property
    def is_connected(self):
        return self.ser is not None and self.ser.is_open
    
    def __del__(self):
        if self.ser is not None:
            self.disconnect()

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

    def exec_macro(self, command, blocking=False, timeout=10):
        path = f"{self.macro_path}/{command}.g"

        trackers = []

        with open(path, 'r') as file:
            lines = file.readlines()

        for line in lines:
            if line[0] == ';':
                continue

            line = re.sub(r'\s*\(.*?\)\s*', '', line).strip()

            for i, name in enumerate(['[posx]', '[posy]', '[posz]']):
                if name in line:
                    self.wait_for_probe(timeout=120)
                    print(f"Replaced {name} with {self.probe_data[i]:.3f} in line: {line}")
                    line = line.replace(name, f"{self.probe_data[i]:.3f}")

            if line == 'M0':
                print("Pausing for user input...")
                # tracker.wait()
                time.sleep(0.5)
                self.wait_for_idle(timeout=120)

                with self.lock:
                    self.paused = True
                tracker = self.send_command('M0')
                trackers.append(tracker)
                time.sleep(0.5)

                input('Press Enter to continue...')
                tracker = self.send_command('~') # Cycle start

                with self.lock:
                    self.paused = False

                trackers.append(tracker)
            else:
                tracker = self.send_command(line)
                if tracker:
                    trackers.append(tracker)

        if blocking:
            for tracker in trackers:
                if tracker:
                    tracker.wait(timeout=timeout)
            
            time.sleep(0.5)
            self.wait_for_idle(timeout=120)
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
        elif message.startswith('['):
            source, values, *rest = message[1:-1].split(':')
            if source == 'PRB':
                self.probe_data = [float(v) for v in values.split(',')]
                print(f"Probe data: {self.probe_data}")
        else:
            print(f"Received message: {message}")
    
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
                self.ser.write((command + '\n').encode('utf-8'))
                self.command_stack.append(tracker)
        
        return tracker
            
    
    def disconnect(self):
        if self.ser is None:
            return
        
        self.ser.close()

        if self.monitor_thread.is_alive():
            self.monitor_thread.stop()
            self.monitor_thread.join()
        
        if self.terminal_thread.is_alive():
            self.terminal_thread.stop()
            self.terminal_thread.join()

        self.ser = None



controller = GRBLController('/dev/ttyACM0')
time.sleep(2)

controller.update_state()
attemps = 3
while attemps > 0:
    tracker = controller.send_command('$H')
    tracker.wait(timeout=60)
    if controller.get_error_state():
        print("Errors detected:", controller.get_error_state())
        controller.clear_errors()
        controller.send_command('$X', blocking=True)
        time.sleep(0.5)
        attemps -= 1
    else:
        print("Homing successful")
        break

time.sleep(0.5)
# time.sleep(5)
print("Moving...")
controller.send_command('G91 G0 X-600 Y-600')

time.sleep(0.5)
controller.wait_for_idle(timeout=120)

print("Current position:", controller.state['MPos'])

time.sleep(0.5)
print("Executing toolchange macro...")
controller.exec_macro('toolchange', blocking=True, timeout=500)
# print("Disconnecting...")

# Could we get a false positive here?
time.sleep(0.5) # Give it time to start moving
controller.wait_for_idle(timeout=120)

print("Tool change complete. Current position:", controller.state['MPos'])

# Move to absolute -600, -600


while controller.is_connected:
    time.sleep(1)



print("done")