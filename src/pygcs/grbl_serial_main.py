from serial.tools import list_ports
from pygcs.serial_comm import GRBLSerial
from pygcs.event_bus import broadcast, consumer
from pygcs.signals import GlobalSignals
import pick
import click
import sys


current_input = ""

def print_received(message):
    """Print message without corrupting current prompt input."""
    sys.stdout.write('\r\033[K')  # Move to start, clear line
    sys.stdout.write(f"[RECEIVED] {message}\n")
    sys.stdout.write(f"> {current_input}")  # Restore prompt and typed text
    sys.stdout.flush()


def main():
    """Main function to list available serial ports."""
    title = 'Select a serial port'
    options = [port.device for port in list_ports.comports()]

    if not options:
        click.echo("No serial ports found.")
        return

    selected_option, index = pick.pick(options, title, indicator='=>', default_index=0)
    click.echo(f'Selected port: {selected_option}')

    baudrate = click.prompt('Enter baud rate', default='115200')
    serial = GRBLSerial(port=selected_option, baudrate=int(baudrate))
    serial.start()

    # Listen for data from GRBL
    @consumer(GlobalSignals.DATA_RECEIVED)
    def handle_data_received(data):
        print_received(data)

    click.echo("Type commands to send to GRBL (type 'exit' to quit).")

    try:
        while True:
            # Manually read input to track typed text
            current_input = click.prompt('> ', prompt_suffix='', default='', show_default=False)
            if current_input.lower() in ('exit', 'quit'):
                break
            broadcast(GlobalSignals.SEND_DATA, current_input)
            current_input = ""  # Reset buffer after sending
    except:
        click.echo("\nExiting...")
    finally:
        serial.disconnect()
        click.echo("Disconnected from serial port.")


if __name__ == "__main__":
    main()
