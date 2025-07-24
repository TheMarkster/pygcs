import threading
from .event_bus import events, broadcast
from .signals import GlobalSignals
import sys
import select

class SimpleTerminal(threading.Thread):
    """A simple terminal interface for receiving commands and sending responses."""
    
    def __init__(self, callback):
        super().__init__(daemon=True)
        self.callback = callback
        self.running = True
        self.lock = threading.RLock()

    # def run(self):
    #     """Run the terminal listener in a separate thread."""
    #     while self.running:
    #         try:
    #             line = input("> ").strip()
    #             if line:
    #                 self.callback(line)
    #         except EOFError:
    #             break
    #         except Exception as e:
    #             print(f"Error: {e}")
        
    #     print("Terminal listener stopped.")

    def run(self):
        try:
            # with self.lock:
                # self.setup_raw_mode()
                # sys.stdout.write("\x1b[2J\x1b[H")
                # sys.stdout.write("Pretty Terminal (Ctrl+C to exit)\n\r")
                # self.redraw_interface()
            
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
    
    @events.consumer(GlobalSignals.LOG)
    def log(self, message: str):
        """Handle log messages from the event bus."""
        print(f"LOG: {message}")
    
    @events.consumer(GlobalSignals.ERROR)
    def error_log(self, message: str):
        """Handle error messages from the event bus."""
        print(f"ERROR: {message}")