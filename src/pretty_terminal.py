import threading
import sys
import termios
import tty
import select
import os
import time
from broadcast import broadcast, Broadcastable, Signal

CLEAR_LINE = '\x1b[2K'
RED = '\x1b[31m'
RESET = '\x1b[0m'

class PrettyTerminal(threading.Thread, Broadcastable):
    USER_RESPONSE = Signal("user_response")
    USER_INPUT = Signal("user_input")

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

    def setup_raw_mode(self):
        """Set terminal to raw mode to intercept all input"""
        if os.isatty(sys.stdin.fileno()):
            self.old_settings = termios.tcgetattr(sys.stdin.fileno())
            tty.setraw(sys.stdin.fileno())

    def restore_terminal(self):
        """Restore terminal to original settings"""
        # Go to the bottom line
        while self.lines_from_bottom > 0:
            sys.stdout.write(f"\x1b[B")
            self.lines_from_bottom -= 1
        
        # We're on the status line now 
        # Move to the end of the line and add a newline
        sys.stdout.write("\r")
        for _ in range(len(self.status_message)+8):
            sys.stdout.write("\x1b[C")
        
        sys.stdout.write("\n\r")
        sys.stdout.flush()

        if self.old_settings and os.isatty(sys.stdin.fileno()):
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self.old_settings)

    def run(self):
        try:
            self.setup_raw_mode()
            # Clear screen and move cursor to top
            sys.stdout.write("\x1b[2J\x1b[H")
            sys.stdout.write("Pretty Terminal (Ctrl+C to exit)\n\r")
            self.redraw_interface()
            
            while self.running:
                if select.select([sys.stdin], [], [], 0.1)[0]:
                    c = sys.stdin.read(1)
                    self.handle_char(c)
        except KeyboardInterrupt:
            pass
        finally:
            self.restore_terminal()

    def handle_char(self, c):
        """Handle individual character input"""
        if ord(c) == 3:  # Ctrl+C
            self.running = False
            return
        elif ord(c) == 4:  # Ctrl+D (EOF)
            self.running = False
            return
        elif c == '\n' or c == '\r':  # Enter key
            # Process the line without showing the newline
            line = self.current_user_input
            self.current_user_input = ""
            if self.user_prompt:
                self.user_prompt = ""
                self.USER_RESPONSE.emit(line)
            else:
                self.USER_INPUT.emit(line)
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

    @broadcast.consumer('status_message')
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
    
    @broadcast.consumer('log')
    def LOG(self, message: str):
        self.print(message)
    
    @broadcast.consumer('error_log')
    def ERROR_LOG(self, message: str):
        self.print(f"{message}", True)

    @broadcast.consumer('prompt_user')
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

listener = PrettyTerminal()
listener.start()

time.sleep(0.1)

@broadcast.consumer('user_response')
def handle_user_response(response: str):
    broadcast.emit('log', f"User responded: '{response}'")

@broadcast.consumer('user_input')
def handle_user_input(command: str):
    broadcast.emit('log', f"User input: '{command}'")

broadcast.emit('status_message', "I'm the current status message!")
broadcast.emit('log', "This is a log message.")
broadcast.emit('error_log', "This is an error log message.")
broadcast.emit('prompt_user', "Enter your name:")



while listener.is_alive():
    listener.join(1)