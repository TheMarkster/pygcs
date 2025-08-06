from pygcs.networking import Server
from pygcs.event_processor import EventProcessor
from pygcs.remote_objects import RemoteObjectServer
from pygcs.controller import GRBLController, SentCommand
from pygcs.serial_comm import GRBLSerial

from pygcs.event_bus import broadcast
from pygcs.signals import GlobalSignals
import time

import argparse

def main():
    thread_pool = []

    parser = argparse.ArgumentParser(description="Start the GCS server")
    parser.add_argument('--host', type=str, default='0.0.0.0', help="Server host")
    parser.add_argument('--port', type=int, default=8888, help="Server port")
    args = parser.parse_args()

    server_host = args.host
    port = args.port

    server = Server(host=server_host, port=port)

    if not server.connect():
        print("❌ Could not start server. Make sure the port is available.")
        return
    
    serial_port = '/dev/ttyACM0'
    serial_baudrate = 115200
    serial = GRBLSerial(port=serial_port, baudrate=serial_baudrate)

    # Listen on another thread and generate events
    serial.start()
    thread_pool.append(serial)

    remote_object_server = RemoteObjectServer()
    remote_object_server.add_allowed_class([GRBLController, SentCommand])
    server.add_processor(remote_object_server)
    controller = GRBLController()
    remote_object_server.register_object(controller)

    while server.running:
        time.sleep(0.5)

    broadcast(GlobalSignals.DISCONNECTED)  # Broadcast disconnect signal when stopping
    
    for thread in thread_pool:
        thread.join()


if __name__ == "__main__":
    main()