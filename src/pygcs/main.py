from pygcs.controller import GRBLController
from pygcs.serial_comm import GRBLSerial
from pygcs.pretty_terminal import PrettyTerminal
from pygcs.event_bridge_server import EventBridgeServer
from pygcs.event_bus import events
from pygcs.signals import GlobalSignals
from pygcs.registry import broadcast, consumer
import time

def main():
    thread_pool = {}

    terminal = PrettyTerminal()
    thread_pool['pretty_terminal'] = terminal
    terminal.start()

    

    serial = GRBLSerial('/dev/ttyUSB0', 115200)
    thread_pool['serial_comm'] = serial
    serial.start()

    server = EventBridgeServer()
    thread_pool['event_bridge'] = server
    events.forward_to(server._forward_event_to_clients)
    server.start()

    # for thread in thread_pool:
    #     thread.start()

    controller = GRBLController()

    controller.exec()

    for name, thread in thread_pool.items():
        print(f"Waiting for {name} thread to exit...")
        thread.join()


if __name__ == "__main__":
    main()