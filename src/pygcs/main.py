from pygcs.controller import Controller
from pygcs.serial_comm import GRBLSerial
from pygcs.pretty_terminal import PrettyTerminal
from pygcs.event_bridge_server import EventBridgeServer
from pygcs.broadcast import get_broadcast
import time

def main():
    thread_pool = []

    controller = Controller()

    terminal = PrettyTerminal()
    thread_pool.append(terminal)

    serial = GRBLSerial('/dev/ttyUSB0', 115200, controller)
    thread_pool.append(serial)

    server = EventBridgeServer()
    thread_pool.append(server)
    get_broadcast().forward_to(server)

    for thread in thread_pool:
        thread.start()

    controller.exec()

    for thread in thread_pool:
        thread.join()


if __name__ == "__main__":
    main()