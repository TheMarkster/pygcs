import threading
import sys
import termios
import tty
import select
import os
import time
from functools import wraps
from .signals import GlobalSignals
from .event_bus import events, Broadcastable, broadcast

CLEAR_LINE = '\x1b[2K'
RED = '\x1b[31m'
RESET = '\x1b[0m'

def synchronize(func):
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        with self.lock:
            return func(self, *args, **kwargs)
        # return
    return wrapper

class PrettyTerminal(threading.Thread, Broadcastable):
    def __init__(self):
        threading.Thread.__init__(self)
        Broadcastable.__init__(self)
        self.current_user_input = ""
        self.escape_buffer = ""
        self.escaped = False
        self.running = True
        self.cursor_position = 0
        self.old_settings = None
        self.daemon = True
        self.user_prompt = ""
        self.status_message = ""
        self.lines_from_bottom = 2
        self.raw_mode = False
        self.lock = threading.RLock()

    def setup_raw_mode(self):
        """Set terminal to raw mode to intercept all input"""
        if os.isatty(sys.stdin.fileno()):
            self.old_settings = termios.tcgetattr(sys.stdin.fileno())
            tty.setraw(sys.stdin.fileno())
            self.raw_mode = True

    def restore_terminal(self):
        """Restore terminal to original settings"""
        # Go to the bottom line
        while self.lines_from_bottom > -1:
            sys.stdout.write(f"\x1b[B")
            self.lines_from_bottom -= 1
        
        # We're on the status line now 
        # Move to the end of the line and add a newline
        sys.stdout.write("\r")
        # for _ in range(len(self.status_message)+8):
        #     sys.stdout.write("\x1b[C")
        
        # sys.stdout.write("\n\r")
        sys.stdout.flush()

        if self.old_settings and os.isatty(sys.stdin.fileno()):
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self.old_settings)
        
        self.raw_mode = False

    def run(self):
        try:
            with self.lock:
                self.setup_raw_mode()
                sys.stdout.write("\x1b[2J\x1b[H")
                sys.stdout.write("Pretty Terminal (Ctrl+C to exit)\n\r")
                self.redraw_interface()
            
            while self.running:
                if select.select([sys.stdin], [], [], 0.1)[0]:
                    c = sys.stdin.read(1)
                    with self.lock:
                        self.handle_char(c)
        except KeyboardInterrupt:
            pass
        finally:
            with self.lock:
                self.restore_terminal()
        
        broadcast(GlobalSignals.LOG, "PrettyTerminal thread exited.")


    def handle_char(self, c):
        """Handle individual character input"""
        if ord(c) == 3:  # Ctrl+C
            broadcast(GlobalSignals.DISCONNECTED)
            return
        elif ord(c) == 4:  # Ctrl+D (EOF)
            broadcast(GlobalSignals.DISCONNECTED)
            return
        elif c == '\n' or c == '\r':  # Enter key
            # Process the line without showing the newline
            line = self.current_user_input
            self.current_user_input = ""
            if self.user_prompt:
                self.user_prompt = ""
                broadcast(GlobalSignals.USER_RESPONSE, line)
            else:
                broadcast(GlobalSignals.USER_INPUT, line)
            self.cursor_position = 0
            
            # Redraw interface after processing input
            self.redraw_input_line()
        elif ord(c) == 127 or ord(c) == 8:  # Backspace/Delete
            if self.cursor_position > 0:
                self.current_user_input = (
                    self.current_user_input[:self.cursor_position-1] + 
                    self.current_user_input[self.cursor_position:]
                )
                self.cursor_position -= 1
                self.redraw_input_line()
                
        elif ord(c) == 27:  # Escape sequence (arrow keys, etc.)
            # Read the rest of the escape sequence
            
            # We already have the stream selected
            seq = sys.stdin.read(2)

            if seq == '[D' and self.cursor_position > 0:  # Left arrow
                self.cursor_position -= 1
                self.redraw_input_line()
            elif seq == '[C' and self.cursor_position < len(self.current_user_input):  # Right arrow
                self.cursor_position += 1
                self.redraw_input_line()
                
        elif ord(c) >= 32 and ord(c) < 127:  # Printable characters
            # Insert character at cursor position
            self.current_user_input = (
                self.current_user_input[:self.cursor_position] + c + 
                self.current_user_input[self.cursor_position:]
            )
            self.cursor_position += 1
            self.redraw_input_line()
    
    def redraw_interface(self):
        """Redraw the complete interface with status and input lines"""
        # Move to bottom of screen and clear last two lines
        while self.lines_from_bottom > 0:
            sys.stdout.write(f"\n\r{CLEAR_LINE}")  # Status line
            self.lines_from_bottom -= 1

        # Buffer line
        sys.stdout.write(f"\x1b[2A\r{CLEAR_LINE}")
        
        # We're on the status line now
        sys.stdout.write(f"\x1b[2B\r{CLEAR_LINE}Status: {self.status_message}")

        # Move up and draw the input prompt
        sys.stdout.write(f"\x1b[1A\r{CLEAR_LINE}{self.user_prompt}> {self.current_user_input}")

        self.lines_from_bottom = 1

        sys.stdout.flush()

    def redraw_input_line(self):
        """Redraw only the input line (faster than full interface redraw)"""
        # Clear current input line and redraw
        sys.stdout.write(f"\r{CLEAR_LINE}{self.user_prompt}> {self.current_user_input}")

        # Position cursor correctly
        chars_after_cursor = len(self.current_user_input) - self.cursor_position
        if chars_after_cursor > 0:
            sys.stdout.write(f"\x1b[{chars_after_cursor}D")
        
        sys.stdout.flush()
    
    @events.consumer(GlobalSignals.DISCONNECTED)
    def disconnect(self):
        """Handle disconnection event"""
        self.running = False
        self.restore_terminal()
        broadcast(GlobalSignals.LOG, "PrettyTerminal disconnected.")

    @events.consumer(GlobalSignals.STATUS_MESSAGE)
    @synchronize
    def update_status_message(self, message: str):
        """Update the status message and redraw interface"""
        self.status_message = message
        # Save cursor position in input
        
        while self.lines_from_bottom > 0:
            sys.stdout.write(f"\x1b[B")
            self.lines_from_bottom -= 1
        
        # Move up to status line and update it
        sys.stdout.write(f"\r{CLEAR_LINE}Status: {self.status_message}")
        
        # Move back to the user input
        sys.stdout.write(f"\x1b[A\r{CLEAR_LINE}{self.user_prompt}> {self.current_user_input}")

        self.lines_from_bottom += 1
        # # Restore cursor position
        # chars_after_cursor = len(input_text) - cursor_pos
        # if chars_after_cursor > 0:
        #     sys.stdout.write(f"\x1b[{chars_after_cursor}D")
        
        sys.stdout.flush()
    
    
    @events.consumer(GlobalSignals.LOG)
    @synchronize
    def LOG(self, message: str):
        if self.raw_mode:
            self.print(message)
        else:
            sys.stdout.write(f"{message}\n\r")
    
    @events.consumer(GlobalSignals.ERROR)
    @synchronize
    def ERROR_LOG(self, message: str):
        if self.raw_mode:
            self.print(f"{message}", True)
        else:
            sys.stdout.write(f"{RED}{message}{RESET}\n\r")

    @events.consumer(GlobalSignals.PROMPT_USER)
    @synchronize
    def prompt_user(self, prompt: str):
        self.user_prompt = prompt
        self.redraw_input_line()

    def print(self, message: str, error=False):
        """Print a message above the status/input lines"""
        # Save current state
        current_line = self.current_user_input
        cursor_pos = self.cursor_position
        
        # Apply color formatting - red when error is True
        if error:
            formatted_message = f"{RED}{message}{RESET}"
        else:
            formatted_message = message

        # Move up to two lines from bottom
        self.lines_from_bottom += 1 # We're going to be longer by one line
        while self.lines_from_bottom < 3:
            sys.stdout.write(f"\x1b[A")
            self.lines_from_bottom += 1
        
        # Move up to above status line, print message
        sys.stdout.write(f"\r{CLEAR_LINE}{formatted_message}")

        self.redraw_interface()

    def stop(self):
        """Stop the terminal listener"""
        self.running = False

# listener = PrettyTerminal()
# listener.start()

# time.sleep(0.1)

# @events.consumer('user_response')
# def handle_user_response(response: str):
#     broadcast.emit('log', f"User responded: '{response}'")

# @events.consumer('user_input')
# def handle_user_input(command: str):
#     broadcast.emit('log', f"User input: '{command}'")

# broadcast.emit('status_message', "I'm the current status message!")
# broadcast.emit('log', "This is a log message.")
# broadcast.emit('error_log', "This is an error log message.")
# broadcast.emit('prompt_user', "Enter your name:")



# while listener.is_alive():
#     listener.join(1)