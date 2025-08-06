from pygcs.controller import GRBLController
from pygcs.networking import Client
from pygcs.event_processor import EventProcessor
from pygcs.remote_objects import ClientProcessor, RemoteObject
import time

import argparse

def test_controller(controller: GRBLController):
    time.sleep(2)

    controller.update_state()
    attempts = 3
    while attempts > 0:
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

def main():
    parser = argparse.ArgumentParser(description="Run the GRBL client")
    parser.add_argument('--host', type=str, default='localhost', help="Server host")
    parser.add_argument('--port', type=int, default=8888, help="Server port")
    args = parser.parse_args()

    client_host = args.host
    port = args.port

    client = Client(server_host=client_host, server_port=port)

    if not client.connect():
        print("❌ Could not connect to server. Make sure it is running.")
        return
    
    api_client = ClientProcessor()
    client.add_processor(api_client)
    obj_ids = api_client.call('list_objects', args=[GRBLController.__name__])
    controller: GRBLController = RemoteObject(obj_ids[0], api_client, GRBLController)

    test_controller(controller)

if __name__ == "__main__":
    main()