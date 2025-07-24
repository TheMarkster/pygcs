# Event Bridge System Documentation

## Overview

The Event Bridge system provides a distributed event architecture that allows multiple processes, applications, or services to share events seamlessly. It consists of:

1. **Event Bridge Server** - Central coordinator that receives events from clients and broadcasts them to all connected clients
2. **Event Bridge Client** - Connects to the server and synchronizes local events with the distributed system
3. **Integration with Broadcast System** - Uses the existing events.consumer system for local event handling

## Architecture

```
┌─────────────┐     ┌─────────────────┐     ┌─────────────┐
│   Client A  │────▶│ Event Bridge    │◀────│   Client B  │
│             │     │     Server      │     │             │
│ Local Events│     │                 │     │Local Events │
│ Broadcast   │     │ Coordinates &   │     │ Broadcast   │
│ System      │     │ Forwards Events │     │ System      │
└─────────────┘     └─────────────────┘     └─────────────┘
       ▲                       ▲                       ▲
       │                       │                       │
       ▼                       ▼                       ▼
┌─────────────┐     ┌─────────────────┐     ┌─────────────┐
│Local Event  │     │Server Events    │     │Local Event  │
│Consumers    │     │& Middleware     │     │Consumers    │
└─────────────┘     └─────────────────┘     └─────────────┘
```

## Key Features

### 1. Bidirectional Event Synchronization
- Events generated on any client are broadcast to all other clients
- Events generated on the server are broadcast to all clients
- Loop prevention ensures events don't bounce back to their source

### 2. Robust Connection Handling
- Automatic reconnection support
- Graceful handling of client disconnections
- Error recovery and logging

### 3. Integration with Existing Broadcast System
- Uses the same `@events.consumer` decorators
- Maintains compatibility with standalone functions and class methods
- Supports namespaces and middleware

### 4. JSON-based Protocol
- Simple, human-readable event format
- Cross-platform compatibility
- Easy to debug and monitor

## Usage Examples

### Starting the Event Bridge Server

```python
from event_bridge_server import EventBridgeServer
import threading

# Create and start server
server = EventBridgeServer(host='localhost', port=8888)
server_thread = threading.Thread(target=server.start, daemon=True)
server_thread.start()

# Server will now coordinate events between clients
```

### Connecting a Client

```python
from event_bridge_client import EventBridgeClient
from broadcast import get_broadcast

# Create and connect client
client = EventBridgeClient(server_host='localhost', 
                          server_port=8888, 
                          client_name='MyApp')
client.connect()

# Set up event handlers (same as local broadcast system)
@get_broadcast().consumer('user_action')
def handle_user_action(action, user=None, **kwargs):
    source = kwargs.get('_source_address', 'local')
    print(f"User {user} performed {action} (from {source})")

# Emit events (will be sent to all connected clients)
get_broadcast().emit('user_action', action='login', user='Alice')
```

### Distributed Chat Application

```python
from chat_example import ChatClient

# Create chat client
chat = ChatClient('Alice')
chat.connect()

# Send messages (distributed to all users)
chat.send_message("Hello everyone!")

# Event handlers automatically receive messages from other users
```

## File Structure

```
src/
├── event_bridge_server.py    # Server implementation
├── event_bridge_client.py    # Client implementation
├── broadcast.py              # Core broadcast system
└── examples/
    ├── chat_example.py       # Distributed chat demo
    ├── test_event_bridge.py  # Basic functionality test
    └── event_bridge_demo.py  # Interactive demo script
```

## Running the Examples

### 1. Basic Test
```bash
python3 test_event_bridge.py
```

### 2. Manual Server + Clients
```bash
# Terminal 1: Start server
python3 src/event_bridge_server.py

# Terminal 2: Start client 1
python3 src/event_bridge_client.py Client1

# Terminal 3: Start client 2  
python3 src/event_bridge_client.py Client2
```

### 3. Chat Application
```bash
# Terminal 1: Start server
python3 src/event_bridge_server.py

# Terminal 2: Start chat client 1
python3 chat_example.py

# Terminal 3: Start chat client 2
python3 chat_example.py

# Or run automated demo:
python3 chat_example.py demo
```

### 4. Interactive Demo
```bash
python3 event_bridge_demo.py
```

## Event Flow

### Local Event → Distributed
1. Local code emits event: `broadcast.emit('user_login', user='Alice')`
2. Client's watcher catches the event
3. Client sends JSON to server: `{"signal": "user_login", "args": [], "kwargs": {"user": "Alice"}}`
4. Server receives and broadcasts to all other clients
5. Other clients emit the event locally with `_remote_event=True` flag

### Remote Event → Local
1. Client receives JSON from server
2. Client parses and emits locally: `broadcast.emit('user_login', user='Alice', _remote_event=True)`
3. Local consumers handle the event normally
4. The `_remote_event` flag prevents re-forwarding

## Configuration

### Server Configuration
```python
server = EventBridgeServer(
    host='0.0.0.0',      # Listen on all interfaces
    port=8888,           # Port number
)
```

### Client Configuration
```python
client = EventBridgeClient(
    server_host='192.168.1.100',  # Server IP
    server_port=8888,             # Server port
    client_name='MyService'       # Unique client identifier
)
```

## Error Handling

The system includes comprehensive error handling:

- **Connection Errors**: Automatic retry and graceful degradation
- **JSON Parse Errors**: Invalid messages are logged and ignored
- **Event Processing Errors**: Exceptions in event handlers don't break the bridge
- **Network Errors**: Clients detect disconnections and can reconnect

## Loop Prevention

The system prevents infinite event loops through:

1. **Remote Event Marking**: Events from remote sources are marked with `_remote_event=True`
2. **Source Filtering**: Watchers ignore events marked as remote
3. **Internal Event Filtering**: System events (instance_*, broadcast_*) are not forwarded

## Best Practices

### 1. Event Design
- Use descriptive signal names: `'user_logged_in'` not `'event1'`
- Include relevant context in event parameters
- Keep event payloads JSON-serializable

### 2. Error Handling
- Always handle potential connection failures
- Log important events for debugging
- Use try-catch blocks around critical event handlers

### 3. Performance
- Avoid high-frequency events that could flood the network
- Consider using batching for rapid event sequences
- Monitor network usage in production

### 4. Security
- Run server on private networks when possible
- Consider adding authentication for production use
- Validate event data on both client and server sides

## Advanced Features

### Custom Event Filtering
```python
# Only forward certain events
def should_forward_event(signal, *args, **kwargs):
    return signal.startswith('public_')

# Apply filter in client watcher
```

### Event Middleware
```python
# Add logging middleware on server
def log_middleware(event_data):
    print(f"Event: {event_data['signal']}")
    return event_data

server.broadcast.add_middleware(log_middleware)
```

### Namespace Isolation
```python
# Create isolated event namespaces
client = EventBridgeClient(client_name='Service1')
service = SomeService(namespace='service1')  # Events isolated to namespace
```

This event bridge system provides a solid foundation for building distributed, event-driven applications while maintaining the simplicity and flexibility of the core broadcast system.
