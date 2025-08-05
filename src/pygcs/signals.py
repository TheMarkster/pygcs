from enum import StrEnum

class GlobalSignals(StrEnum):
    # Logging
    LOG = "log"
    ERROR = "error_log"

    # Controller signals
    STATUS_UPDATED = "status_message"
    SHUTDOWN = "shutdown"
    GCODE_SENT = "gcode_sent"
    MCODE_SENT = "mcode_sent"

    EXEC_MACRO = "exec_macro"
    LOAD_PROGRAM = "load_program"
    PROGRAM_START = "program_start"
    PROGRAM_STOP = "program_stop"
    PROGRAM_PAUSE = "program_pause"
    PROGRAM_RESUME = "program_resume"

    # Serial interface signals
    DATA_RECEIVED = "data_received"
    DATA_SENT = "data_sent"
    DISCONNECTED = "disconnected"
    SEND_DATA = "grbl_send"
    # SEND_DATA = Signal("SEND_DATA"

    # Terminal signals
    USER_RESPONSE = "user_response"
    USER_INPUT = "user_input"
    PROMPT_USER = "prompt_user"
    STATUS_MESSAGE = "status_message"
