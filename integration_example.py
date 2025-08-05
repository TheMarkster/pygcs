"""
Integration example showing how to use PrintInterceptor with the event bus system
"""

from src.pygcs.print_interceptor import PrintInterceptor, LogEvent, create_event_bus_logger
from src.pygcs.event_bus import get_event_bus


def setup_print_logging():
    """Setup print interception to work with the event bus"""
    
    # Get the event bus instance
    event_bus = get_event_bus()
    
    # Create a log handler that broadcasts to the event bus
    def event_bus_log_handler(event: LogEvent):
        """Send print events to the event bus"""
        try:
            event_bus.broadcast('print_intercepted', {
                'timestamp': event.timestamp.isoformat(),
                'message': event.message,
                'source': {
                    'file': event.caller_file,
                    'function': event.caller_function,
                    'line': event.caller_line
                },
                'thread': {
                    'id': event.thread_id,
                    'name': event.thread_name
                }
            })
        except Exception as e:
            # Fallback to console if event bus fails
            print(f"❌ Failed to send print event to event bus: {e}")
    
    return event_bus_log_handler


def setup_print_event_handlers():
    """Setup event handlers to listen for print events"""
    
    event_bus = get_event_bus()
    
    @event_bus.on('print_intercepted')
    def handle_print_event(data):
        """Handle intercepted print events"""
        timestamp = data['timestamp']
        message = data['message']
        source = data['source']
        thread = data['thread']
        
        # You can process the print event however you want
        print(f"📝 [PRINT LOG] {timestamp} | "
              f"Thread: {thread['name']} | "
              f"Function: {source['function']}() | "
              f"Message: {message}")
    
    @event_bus.on('print_intercepted')
    def log_to_file(data):
        """Log print events to file"""
        with open('application_prints.log', 'a') as f:
            f.write(f"{data['timestamp']} - {data['message']}\n")
    
    @event_bus.on('print_intercepted')
    def detect_error_prints(data):
        """Detect error-related print statements"""
        message = data['message'].lower()
        if any(keyword in message for keyword in ['error', 'fail', 'exception', '❌']):
            event_bus.broadcast('error_detected', {
                'type': 'print_error',
                'message': data['message'],
                'source': data['source'],
                'timestamp': data['timestamp']
            })


class ApplicationWithPrintLogging:
    """Example application that uses print interception"""
    
    def __init__(self):
        self.event_bus = get_event_bus()
        self.print_log_handler = setup_print_logging()
        setup_print_event_handlers()
    
    def run_with_print_logging(self):
        """Run the application with print logging enabled"""
        
        print("Starting application without logging...")
        
        with PrintInterceptor(self.print_log_handler):
            print("🚀 Application started with print logging")
            
            self.do_some_work()
            self.simulate_error()
            self.do_more_work()
            
            print("✅ Application completed")
        
        print("Application finished - print logging disabled")
    
    def do_some_work(self):
        """Simulate some application work"""
        print("📊 Processing data...")
        print("🔄 Connecting to database...")
        print("✅ Database connection established")
    
    def simulate_error(self):
        """Simulate an error condition"""
        print("❌ Error: Failed to process item 42")
        print("⚠️ Warning: Retrying operation...")
    
    def do_more_work(self):
        """More application work"""
        print("📈 Generating reports...")
        print("📤 Sending notifications...")


# Global print interceptor for the entire application
class GlobalPrintInterceptor:
    """Singleton for managing global print interception"""
    
    _instance = None
    _interceptor = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def start(self):
        """Start global print interception"""
        if self._interceptor is None:
            log_handler = setup_print_logging()
            self._interceptor = PrintInterceptor(log_handler)
            self._interceptor.__enter__()
            print("🔍 Global print interception started")
    
    def stop(self):
        """Stop global print interception"""
        if self._interceptor is not None:
            self._interceptor.__exit__(None, None, None)
            self._interceptor = None
            print("🔍 Global print interception stopped")
    
    def is_active(self):
        """Check if print interception is active"""
        return self._interceptor is not None


def example_usage():
    """Example of how to use the print interceptor with event bus"""
    
    print("=== Print Interceptor + Event Bus Integration ===")
    
    # Method 1: Context manager approach
    print("\n--- Method 1: Context Manager ---")
    app = ApplicationWithPrintLogging()
    app.run_with_print_logging()
    
    # Method 2: Global interceptor approach
    print("\n--- Method 2: Global Interceptor ---")
    global_interceptor = GlobalPrintInterceptor()
    
    global_interceptor.start()
    print("This print is globally intercepted")
    print("So is this one")
    global_interceptor.stop()
    
    print("This print is not intercepted")


if __name__ == "__main__":
    example_usage()
