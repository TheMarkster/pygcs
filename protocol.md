# GRBL Control Server Protocol

The GRBL Control Server runs on port 1234 and provides a JSON-based protocol for remote control and monitoring of the GRBL CNC controller.

## Connection

Connect to the server using a TCP socket on port 1234. All messages are JSON-formatted and terminated with a newline character.

## Message Format

### Request Format
```json
{
    "command": "command_name",
    "parameter1": "value1",
    "parameter2": "value2"
}
```

### Response Format
```json
{
    "success": true,
    "message": "Operation completed successfully"
}
```

### Error Response Format
```json
{
    "error": "Error description"
}
```

### Event Format (Broadcast)
```json
{
    "type": "event",
    "event": "event_name",
    "data": {
        "key": "value"
    },
    "timestamp": 1642781234.567
}
```

## Commands

### 1. Send Program
Upload a G-code program to the server.

**Request:**
```json
{
    "command": "send_program",
    "name": "program_name",
    "content": "G21\nG90\nG0 X10 Y10\n..."
}
```

**Response:**
```json
{
    "success": true,
    "message": "Program 'program_name' uploaded"
}
```

### 2. Start Program
Start execution of a previously uploaded program.

**Request:**
```json
{
    "command": "start_program",
    "name": "program_name"
}
```

**Response:**
```json
{
    "success": true,
    "message": "Program 'program_name' started"
}
```

### 3. Stop Program
Stop the currently running program.

**Request:**
```json
{
    "command": "stop_program"
}
```

**Response:**
```json
{
    "success": true,
    "message": "Program 'program_name' stopped"
}
```

### 4. Resume Program
Resume a paused program.

**Request:**
```json
{
    "command": "resume_program"
}
```

**Response:**
```json
{
    "success": true,
    "message": "Program resumed"
}
```

### 5. Adjust Feed Rate
Adjust the feed rate override (10% to 200%).

**Request:**
```json
{
    "command": "adjust_feed_rate",
    "percentage": 150
}
```

**Response:**
```json
{
    "success": true,
    "message": "Feed rate set to 150%"
}
```

### 6. Get Status
Get current machine status and position.

**Request:**
```json
{
    "command": "get_status"
}
```

**Response:**
```json
{
    "success": true,
    "status": {
        "connected": true,
        "position": {
            "x": 10.5,
            "y": -5.2,
            "z": 2.0
        },
        "state": {
            "MPos": [10.5, -5.2, 2.0],
            "Bf": [15, 128],
            "Fs": [0, 500],
            "Ov": [100, 100, 100]
        },
        "idle": true,
        "current_program": null,
        "errors": []
    }
}
```

### 7. Terminal Command
Send a direct G-code command to the machine.

**Request:**
```json
{
    "command": "terminal_command",
    "gcode": "G0 X10 Y10"
}
```

**Response:**
```json
{
    "success": true,
    "message": "Command 'G0 X10 Y10' sent"
}
```

### 8. List Programs
Get a list of all uploaded programs.

**Request:**
```json
{
    "command": "list_programs"
}
```

**Response:**
```json
{
    "success": true,
    "programs": ["program1", "program2", "test_square"]
}
```

## Events (Broadcasts)

The server broadcasts events to all connected clients automatically.

### program_uploaded
Fired when a new program is uploaded.
```json
{
    "type": "event",
    "event": "program_uploaded",
    "data": {"name": "program_name"},
    "timestamp": 1642781234.567
}
```

### program_started
Fired when a program starts execution.
```json
{
    "type": "event",
    "event": "program_started",
    "data": {"name": "program_name"},
    "timestamp": 1642781234.567
}
```

### program_stopped
Fired when a program is stopped.
```json
{
    "type": "event",
    "event": "program_stopped",
    "data": {"name": "program_name"},
    "timestamp": 1642781234.567
}
```

### program_completed
Fired when a program completes successfully.
```json
{
    "type": "event",
    "event": "program_completed",
    "data": {"name": "program_name"},
    "timestamp": 1642781234.567
}
```

### program_error
Fired when a program encounters an error.
```json
{
    "type": "event",
    "event": "program_error",
    "data": {
        "name": "program_name",
        "error": "Error description"
    },
    "timestamp": 1642781234.567
}
```

### program_resumed
Fired when a program is resumed after being paused.
```json
{
    "type": "event",
    "event": "program_resumed",
    "data": {"name": "program_name"},
    "timestamp": 1642781234.567
}
```

### feed_rate_changed
Fired when the feed rate is adjusted.
```json
{
    "type": "event",
    "event": "feed_rate_changed",
    "data": {"percentage": 150},
    "timestamp": 1642781234.567
}
```

### status_update
Fired periodically with machine status updates.
```json
{
    "type": "event",
    "event": "status_update",
    "data": {
        "raw_message": "<Idle|MPos:0.000,0.000,0.000|Bf:15,128|Fs:0,0|Ov:100,100,100>",
        "state": {
            "MPos": [0.0, 0.0, 0.0],
            "Bf": [15, 128],
            "Fs": [0, 0],
            "Ov": [100, 100, 100]
        }
    },
    "timestamp": 1642781234.567
}
```

## Error Codes

- `"Missing program name or content"` - Required parameters not provided
- `"Program 'name' not found"` - Requested program doesn't exist
- `"A program is already running"` - Cannot start program while another is active
- `"No program is currently running"` - Cannot stop/resume when no program is active
- `"Missing feed rate percentage"` - Feed rate percentage not provided
- `"Feed rate must be between 10% and 200%"` - Invalid feed rate value
- `"Missing gcode command"` - G-code command not provided
- `"Unknown command: command_name"` - Invalid command received
- `"Invalid JSON format"` - Malformed JSON message

## Example Usage

See `client_example.py` for a complete Python client implementation demonstrating all protocol features.
