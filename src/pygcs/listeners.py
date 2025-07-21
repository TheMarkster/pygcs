import threading
import serial
import sys
from old.signals_slots import Signal, Slot, Emitter

class GRBLListener(threading.Thread):
    COMMAND_RECEIVED = Emitter("command_received")


    def __init__(self, ser: serial.Serial, callback):
        super().__init__()
        self.callback = callback
        self.ser = ser
        self.running = True
    
    @property
    def ser(self) -> serial.Serial:
        return self.ser

    def run(self):
        while self.running:
            try:
                line = self.ser.readline().decode('utf-8').rstrip()
                if line:
                    self.callback(line)
            except:
                pass

    def stop(self):
        self.running = False

class TerminalListener(threading.Thread):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback
        self.running = True
    
    @property
    def ser(self) -> serial.Serial:
        return self.controller.ser
    
    def run(self):
        while self.running:
            try:
                line = sys.stdin.readline().rstrip()
                print(f"\r> {line}")
                self.callback(line)
            except:
                pass

    def stop(self):
        self.running = False