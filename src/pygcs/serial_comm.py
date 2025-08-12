import serial
import threading
from .signals import GlobalSignals
from .event_bus import Broadcastable, broadcast, consumer, local_broadcast

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
                    # print(f"Received: {line}")
            except Exception as e:
                if self.running:
                    print("ERROR:" + f"Serial read error: {e}")
                    # local_broadcast(GlobalSignals.DISCONNECTED, )
        print("Serial listener thread exited.")

    @consumer(GlobalSignals.SEND_DATA)
    def send_command(self, command: str):
        if self.ser.is_open:
            command_str = command.strip() + '\n'
            self.ser.write(command_str.encode('utf-8'))
            self.ser.flush()
            broadcast(GlobalSignals.DATA_SENT, command_str)
        else:
            broadcast(GlobalSignals.ERROR_LOG, "Serial port is not open")

    @consumer(GlobalSignals.DISCONNECTED)
    def disconnect(self):
        self.running = False
        if self.ser.is_open:
            self.ser.close()
            self.ser = None