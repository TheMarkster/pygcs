from .handler import EventHandler
from .runtime import get_event_host

class EchoHandler(EventHandler):
    """
    An event handler that echoes the event data to the console.
    """

    def __init__(self):
        super().__init__(name="EchoHandler")
        get_event_host().forward_to(self)
    
    def __del__(self):
        get_event_host().remove_forwarding(self)
    
    def process(self, event):
        print(f"Echoing event: {event}")
        return event
