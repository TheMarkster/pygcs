from .broadcast import Signal, Broadcastable

if 'SIGNALS_MODULE' in globals():
    raise Exception("signals.py loaded multiple times!")
else:
    SIGNALS_MODULE = True

class GlobalSignals(Broadcastable):
    # Logging
    LOG = Signal("log")
    ERROR = Signal("error_log")

    # Controller signals
    STATUS_UPDATED = Signal("status_message")
    SHUTDOWN = Signal("shutdown")
    GCODE_SENT = Signal("gcode_sent")
    MCODE_SENT = Signal("mcode_sent")

    EXEC_MACRO = Signal("exec_macro")
    LOAD_PROGRAM = Signal("load_program")
    PROGRAM_START = Signal("program_start")
    PROGRAM_STOP = Signal("program_stop")
    PROGRAM_PAUSE = Signal("program_pause")
    PROGRAM_RESUME = Signal("program_resume")

    # Serial interface signals
    DATA_RECEIVED = Signal("data_received")
    DATA_SENT = Signal("data_sent")
    DISCONNECTED = Signal("disconnected")
    SEND_DATA = Signal("grbl_send")
    # SEND_DATA = Signal("SEND_DATA")

    # Terminal signals
    USER_RESPONSE = Signal("user_response")
    USER_INPUT = Signal("user_input")
    PROMPT_USER = Signal("prompt_user")
    STATUS_MESSAGE = Signal("status_message")

    def __init__(self):
        super().__init__()

signals = GlobalSignals()