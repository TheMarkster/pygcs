from controller import Controller
from serial_comm import GRBLSerial
from pretty_terminal import PrettyTerminal
import time

# def test(controller: Controller):
    # time.sleep(2)

    # controller.update_state()
    # attempts = 3
    # while attempts > 0:
    #     tracker = controller.send_command('$H')
    #     tracker.wait(timeout=60)
    #     if controller.get_error_state():
    #         print("Errors detected:", controller.get_error_state())
    #         controller.clear_errors()
    #         controller.send_command('$X', blocking=True)
    #         time.sleep(0.5)
    #         attemps -= 1
    #     else:
    #         print("Homing successful")
    #         break

    # time.sleep(0.5)
    # # time.sleep(5)
    # print("Moving...")
    # controller.send_command('G91 G0 X-600 Y-600')

    # time.sleep(0.5)
    # controller.wait_for_idle(timeout=120)

    # print("Current position:", controller.state['MPos'])

    # time.sleep(0.5)
    # print("Executing toolchange macro...")
    # controller.exec_macro('toolchange', blocking=True, timeout=500)
    # # print("Disconnecting...")

    # # Could we get a false positive here?
    # time.sleep(0.5) # Give it time to start moving
    # controller.wait_for_idle(timeout=120)

    # print("Tool change complete. Current position:", controller.state['MPos'])

    # Move to absolute -600, -600


    # while controller.is_connected:
    #     time.sleep(1)

    # print("done")

if __name__ == "__main__":
    thread_pool = []

    controller = Controller()

    terminal = PrettyTerminal()
    thread_pool.append(terminal)

    serial = GRBLSerial('/dev/ttyUSB0', 115200, controller)
    thread_pool.append(serial)

    event_server = EventServer(broadcast)
    thread_pool.append(event_server)

    terminal.start()
    serial.start()
    event_server.start()
    controller.exec()

    for thread in thread_pool:
        thread.join()

    