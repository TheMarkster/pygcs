import builtins
from .host import EventHost, Broadcastable, events
from .event import Event, broadcast_func, get_metastate
from .handler import EventHandler
from .runtime import get_event_host, consumer, broadcast, local_broadcast

def intercept_print(event):
    @broadcast_func
    def inner(*values: object, sep: str | None = " ", end: str | None = "\n", 
              file = None, flush: bool = False):
        message = sep.join(str(value) for value in values)
        # caller_frame = inspect.currentframe().f_back
        # caller_function = caller_frame.f_code.co_name
        # caller_class = caller_frame.f_globals.get('__name__', 'unknown')
        # # caller_line = caller_frame.f_lineno
        # # timestamp = datetime.now()
        # # thread_name = threading.current_thread().name

        # _metadata = {
        #     'message': message,
        #     'caller_function': caller_function,
        #     'caller_class': caller_class,
        # }

        # broadcast(GlobalSignals.LOG, message, _metadata=_metadata)
        local_broadcast(event, message)
    return inner