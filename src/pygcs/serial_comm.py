from .event_bus import Broadcastable, events, broadcast
import serial
import threading
from .signals import GlobalSignals

class GRBLSerial(threading.Thread, Broadcastable):

    def __init__(self, port, baudrate=115200):
        threading.Thread.__init__(self, daemon=True)
        Broadcastable.__init__(self)

        self.ser = serial.Serial(port, baudrate, timeout=1)
        self.ser.flush()
        self.running = False

    def run(self):
        self.running = True
        while self.running:
            try:
                line = self.ser.readline().decode('utf-8').rstrip()
                if line:
                    broadcast(GlobalSignals.DATA_RECEIVED, line)
                    broadcast(GlobalSignals.LOG, f"Received: {line}")
            except Exception as e:
                if self.running:
                    broadcast(GlobalSignals.ERROR, f"Serial read error: {e}")
                    broadcast(GlobalSignals.DISCONNECTED, )
        broadcast(GlobalSignals.LOG, "Serial listener thread exited.")

    @events.consumer(GlobalSignals.SEND_DATA)
    def send_command(self, command: str):
        if self.ser.is_open:
            command_str = command.strip() + '\n'
            self.ser.write(command_str.encode('utf-8'))
            self.ser.flush()
            broadcast(GlobalSignals.DATA_SENT, command_str)
        else:
            broadcast(GlobalSignals.ERROR_LOG, "Serial port is not open")

    @events.consumer(GlobalSignals.DISCONNECTED)
    def disconnect(self):
        self.running = False
        if self.ser.is_open:
            self.ser.close()
            self.ser = None