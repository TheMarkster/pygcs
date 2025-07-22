from .broadcast import Broadcastable, Signal, broadcast
import serial
import threading
from .signals import signals

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
                    signals.DATA_RECEIVED.emit(line)
                    signals.LOG.emit(f"Received: {line}")
            except Exception as e:
                if self.running:
                    signals.ERROR.emit(f"Serial read error: {e}")
                    signals.DISCONNECTED.emit()
        signals.LOG.emit("Serial listener thread exited.")

    @broadcast.consumer(signals.SEND_DATA)
    def send_command(self, command: str):
        if self.ser.is_open:
            command_str = command.strip() + '\n'
            self.ser.write(command_str.encode('utf-8'))
            self.ser.flush()
            signals.DATA_SENT.emit(command_str)
        else:
            signals.ERROR_LOG.emit("Serial port is not open")

    @broadcast.consumer(signals.DISCONNECTED)
    def disconnect(self):
        self.running = False
        if self.ser.is_open:
            self.ser.close()
            self.ser = None