from broadcast import Broadcastable, Signal, broadcast
import serial
import threading

class GRBLSerial(threading.Thread, Broadcastable):
    DATA_RECEIVED = Signal("data_received")
    DATA_SENT = Signal("data_sent")
    DISCONNECTED = Signal("disconnected")
    ERROR = Signal("error")

    DISCONNECT = Slot("disconnect")
    SEND_DATA = Slot("send_data")

    def __init__(self, port, baudrate=115200):
        super().__init__()
        self.ser = serial.Serial(port, baudrate, timeout=1)
        self.ser.flush()

    def run(self):
        while True:
            try:
                line = self.ser.readline().decode('utf-8').rstrip()
                if line:
                    self.DATA_RECEIVED.emit(line)
            except Exception as e:
                self.DISCONNECTED.emit()

    @SEND_DATA.register
    def send_command(self, command: str):
        if self.ser.is_open:
            command_str = command.strip() + '\n'
            self.ser.write(command_str.encode('utf-8'))
            self.ser.flush()
            self.DATA_SENT.emit(command_str)
        else:
            self.ERROR.emit("Serial port is not open")

    @DISCONNECT.register
    def disconnect(self):
        if self.ser.is_open:
            self.ser.close()
            self.ser = None