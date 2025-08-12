from pygcs.event_bus import broadcast, consumer
from pygcs.signals import GlobalSignals
from pygcs.controller import GRBLController
from pygcs.serial_comm import GRBLSerial
import time

import sys
import threading

current_input = ""

def terminal_run():
    import click

    click.echo("Type commands to send to GRBL (type 'exit' to quit).")

    try:
        while True:
            # Manually read input to track typed text
            current_input = click.prompt('> ', prompt_suffix='', default='', show_default=False)
            if current_input.lower() in ('exit', 'quit'):
                break
            broadcast("queue_immediate", current_input)
            current_input = ""  # Reset buffer after sending
    except:
        pass
    finally:
        broadcast(GlobalSignals.DISCONNECTED)

class PrintInterceptor:
    def __init__(self):
        self.original_stdout = sys.stdout
        self.lock = threading.Lock()
    
    def __enter__(self):
        sys.stdout = self  # Redirect stdout to this instance
        return self
    
    def __exit__(self, exc_type, exc_value, traceback):
        sys.stdout = self.original_stdout

    def write(self, data):
        """Intercept print statements and handle them"""
        with self.lock:
            data = data.strip()
            if not data:
                return
            
            if isinstance(data, bytes):
                data = data.decode('utf-8')

            self.original_stdout.write('\r\033[K')  # Move to start, clear line
            self.original_stdout.write(data + '\n')
            self.original_stdout.write(f"> {current_input}")  # Restore prompt and typed text
            self.original_stdout.flush()
    
    def flush(self):
        """Flush method to comply with file-like interface"""
        self.original_stdout.flush()

def main():
    from pygcs.serial_comm import GRBLSerial
    from pygcs.event_bus.echo import EchoHandler
    from serial.tools import list_ports
    import click
    import pick

    title = 'Select a serial port'
    options = [port.device for port in list_ports.comports()]

    if not options:
        click.echo("No serial ports found.")
        return

    selected_option, index = pick.pick(options, title, indicator='=>', default_index=0)
    click.echo(f'Selected port: {selected_option}')

    baudrate = click.prompt('Enter baud rate', default='115200')

    with PrintInterceptor():
        serial = GRBLSerial(port=selected_option, baudrate=int(baudrate))
        serial.start()

        # Listen for data from GRBL
        @consumer(GlobalSignals.DATA_RECEIVED)
        def handle_data_received(data):
            print("[RECEIVED] " + data)

        @consumer(GlobalSignals.SEND_DATA)
        def handle_data_received(data):
            print("[SENT]" + data)

        
        terminal_thread = threading.Thread(target=terminal_run, daemon=True)
        terminal_thread.start()

        # echo_handler = EchoHandler()
        
        try:
            time.sleep(2)  # Allow time for serial connection to stabilize

            controller = GRBLController()
            main_thread = threading.Thread(target=controller.exec, daemon=True)
            main_thread.start()

            future = controller.home()
            # TODO: Home currently doesn't return a future, so we can't wait on it
            # Implement a future the works with retries
            # future.wait()

            future = controller.exec_macro('toolchange')
            future.wait()

            program_code = """G21
                G90
                G0 X0Y0
                G91 G0 X-600 Y-600
                G1 X100 F1000
                G1 Y100
                G1 X-100
                G1 Y-100"""

            program = controller.load_program(program_code)
            controller.program_start()
            program.wait()
            controller.wait_for_idle()
            pass
        finally:
            # serial.disconnect()
            # controller.shutdown()
            print("Controller shutdown complete.")


if __name__ == "__main__":
    main()