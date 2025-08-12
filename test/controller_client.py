from pygcs.controller.controller import GRBLController
from pygcs.networking import Client
from pygcs.event_processor import EventProcessor
from pygcs.event_bus import intercept_print, local_broadcast
from pygcs.remote_objects import ClientProcessor, RemoteObject
from pygcs.pretty_terminal import PrettyTerminal
from pygcs.print_interceptor import PrintInterceptor
import numpy as np
import time

import argparse

def test_controller(controller: GRBLController):
    time.sleep(1) # Allow time for connection to stabilize

    controller.update_state()
    attempts = 3
    while attempts > 0:
        tracker = controller.queue_command('$H')
        tracker.wait(timeout=60)
        if controller.get_error_state():
            print("Errors detected:", controller.get_error_state())
            controller.clear_errors()
            controller.queue_command('$X', blocking=True)
            time.sleep(0.5)
            attemps -= 1
        else:
            print("Homing successful")
            break

    time.sleep(0.5)
    # time.sleep(5)
    print("Moving...")
    controller.queue_command('G91 G0 X-600 Y-600')

    time.sleep(0.5)
    controller.wait_for_idle(timeout=120)

    print("Current position:", controller.state['MPos'])

    time.sleep(0.5)
    print("Executing toolchange macro...")
    controller.exec_macro('toolchange')
    # print("Disconnecting...")

    # Could we get a false positive here?
    time.sleep(0.5) # Give it time to start moving
    controller.wait_for_idle(timeout=120)

    print("Tool change complete. Current position:", controller.state['MPos'])

    # Move to absolute -600, -600


    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Keyboard interrupt received, stopping controller...")
        # controller.stop()

    print("done")


test_program = """G21"""

def test_controller2(controller: GRBLController):
    if not controller.state.homed:
        controller.home()
        controller.wait() # Wait for all commands to complete and the machine to be idle

    xbnds, ybnds = controller.get_bounds()

    controller.rapid_move(xbnds.mean(), ybnds.mean())
    controller.wait()

    controller.execute_macro('toolchange')
    controller.wait()

    controller.load_program(test_program)
    controller.start_program()
    controller.wait()

def surface_probe(controller: GRBLController):
    input("Move to approximately 1-inch above surface...")
    safe_z = controller.get_position()[2]

    input("Move to lower left corner annd press Enter...")
    bottom_left = controller.get_position()[:2]

    input("Move to upper right corner and press Enter...")
    top_right = controller.get_position()[:2]
    
    controller.rapid_move_z(safe_z)
    controller.rapid_move_xy(bottom_left[0], bottom_left[1])

    x = np.linspace(bottom_left[0], top_right[0], 10)
    y = np.linspace(bottom_left[1], top_right[1], 10)
    X, Y = np.meshgrid(x, y)

    Z = np.zeros_like(X)
    for i, (xi, yi) in enumerate(zip(X.flatten(), Y.flatten())):
        controller.rapid_move_xy(xi, yi)
        z = controller.probe_z()
        controller.wait()
        Z.flat[i] = z
    
    return X, Y, Z

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
    
    # Event processing
    event_processor = EventProcessor()
    client.add_processor(event_processor)
    
    pretty_terminal = PrettyTerminal()
    pretty_terminal.start()
    
    with PrintInterceptor(intercept_print("log")):
        api_client = ClientProcessor()
        client.add_processor(api_client)
        local_broadcast("log", "Test")
        time.sleep(1)
        obj_ids = api_client.call('list_objects', args=[GRBLController.__name__])
        controller: GRBLController = RemoteObject(obj_ids[0], api_client, GRBLController)

        test_controller(controller)

    # pretty_terminal.join()

if __name__ == "__main__":
    main()