from .event_bus import EventHandler, events, Event
from .signals import GlobalSignals
from .networking import Server, write_message, Message, MessageProcessor, NetworkObject, SocketConnection
# from .event_bus import local_print as print
import socket

class EventProcessor(MessageProcessor, EventHandler):
    def __init__(self, name=None):
        MessageProcessor.__init__(self, 'event')
        if name is None:
            EventHandler.__init__(self)
        else:
            EventHandler.__init__(self, name)
        events.forward_to(self)
        self.forward_to(events)
        self._server = None  # Will be set when attached to a server
    
    def __del__(self):
        events.remove_forwarding(self)

    def process_message(self, message: Message, client_socket: socket.socket, address: tuple) -> bool:
        if message.content != self.content_type:
            return False

    def process_message(self, message: Message, client_socket: socket.socket, address: tuple) -> bool:
        """Process incoming events and forward them to all connected clients"""
        try:
            event = Event.from_dict(message.data)
            print(f"📥 Received event '{event.signal}' with args {event.args} from {address}")
            event.push_path(self.get_path_name(client_socket))
            self.receive(event)
            # print(f"📤 Received signal '{event.signal}' and message '{event.args}' from {address}")
        except Exception as e:
            print(f"❌ Error processing event from {address}: {e}")

    def get_path_name(self, client_socket: socket.socket) -> str:
        """Get a string representation of the client address"""
        if isinstance(client_socket, SocketConnection):
            return self.get_path_name(client_socket.sock)

        try:
            return str(client_socket.getpeername())
        except:
            return "unknown"

    def process(self, event: Event) -> Event:
        """Forward local events to all connected clients"""
        message = Message(
            content='event',
            data=event.to_dict()
        )

        if event._metadata.get('_local_only', False):
            # Don't send local-only events to other devices
            return event
        
        # Get the device list to avoid sending back to devices that have already seen this event
        devices, _ = event.get_path_data()

        for socket in self.server.connections:
            device_name = self.get_path_name(socket)
            if device_name in devices:
                continue

            socket.send_message(message)
        
        return event
