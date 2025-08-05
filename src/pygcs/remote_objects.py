from __future__ import annotations

from pygcs.networking import Client, Server, MessageProcessor, Message
from dataclasses import dataclass
import socket
from concurrent.futures import Future, ThreadPoolExecutor
import threading
from typing import Dict, List, Literal, Any
from functools import wraps

global id_lock, max_request, available_request_ids
id_lock = threading.Lock()
max_request = 1
available_request_ids = [1]

def get_request_id():
    """Get a unique request ID"""
    global max_request, available_request_ids
    with id_lock:
        if len(available_request_ids) > 0:
            return available_request_ids.pop(0)
        else:
            start_id = max_request
            max_request *= 2
            available_request_ids.extend(range(start_id, max_request))
            return available_request_ids.pop(0)

def release_request_id(request_id):
    """Release a request ID back to the pool"""
    global available_request_ids
    with id_lock:
        available_request_ids.append(request_id)

@dataclass
class RemoteCall:
    """Base class for remote calls with common functionality"""
    is_response: bool = False
    result: any = None
    error: str = None
    message_id: str = None
    call_type: str = None  # 'method', 'property_get', 'property_set'
    call_data: dict = None

    def __post_init__(self):
        if self.message_id is None:
            self.message_id = f"request-{get_request_id()}"

    def set_result(self, result: any):
        """Set the result of the remote call"""
        self.result = result
        self.is_response = True
        return self
    
    def set_error(self, error: str):
        """Set an error for the remote call"""
        self.error = error
        self.is_response = True
        return self
    
    def create_response(self, result: any = None, error: str = None):
        """Create a response copy of this call with result or error"""
        response = self.__class__(**{k: v for k, v in self.__dict__.items()})
        response.is_response = True
        response.message_id = self.message_id  # Keep same message ID for correlation
        
        if error is not None:
            response.error = error
            response.result = None
        else:
            response.result = result
            response.error = None
            
        return response
    
    def is_success(self) -> bool:
        """Check if this is a successful response"""
        return self.is_response and self.error is None
    
    def is_error(self) -> bool:
        """Check if this is an error response"""
        return self.is_response and self.error is not None
    
    @staticmethod
    def from_message(message: Message) -> RemoteCall:
        """Create instance from a Message object"""
        data = message.data
        return RemoteCall(
            is_response=data.get("is_response", False),
            result=data.get("result"),
            error=data.get("error"),
            message_id=data.get("message_id"),
            call_type=data.get("call_type"),
            call_data=data.get("call_data", {})
        )

    def to_message(self) -> Message:
        """Convert to a Message object"""
        return Message(content="remote_call", data=self.__dict__)
    
    def __str__(self):
        if self.is_response:
            if self.error:
                return f"{self.__class__.__name__}(response, error='{self.error}', id={self.message_id})"
            else:
                return f"{self.__class__.__name__}(response, result={self.result}, id={self.message_id})"
        else:
            return f"{self.__class__.__name__}(request, id={self.message_id})"

class RemoteCallBase:    
    def get_call_type(self):
        raise NotImplementedError("Subclasses must implement get_call_type()")
    
    def to_remote_call(self) -> RemoteCall:
        """Convert to a RemoteCall object"""
        return RemoteCall(
            call_type=self.get_call_type(),
            call_data=self.__dict__
        )

@dataclass
class RemoteObjectCall(RemoteCallBase):
    """Data structure for remote object calls"""
    obj_id: str = None
    attr_name: str = None
    args: list = None
    kwargs: dict = None

    def __post_init__(self):
        if self.args is None:
            self.args = []
        if self.kwargs is None:
            self.kwargs = {}
    
    @classmethod
    def get_call_type(cls) -> str:
        return 'remote_object_call'

@dataclass
class RemoteObjectGet(RemoteCallBase):
    """Data structure for remote object calls"""
    obj_id: str = None
    attr_name: str = None
    
    @classmethod
    def get_call_type(cls) -> str:
        return 'remote_object_get'

@dataclass
class RemoteObjectSet(RemoteCallBase):
    """Data structure for remote object calls"""
    obj_id: str = None
    attr_name: str = None
    value: Any = None
    
    @classmethod
    def get_call_type(cls) -> str:
        return 'remote_object_set'

@dataclass
class APIRequest(RemoteCallBase):
    func_name: str = None
    args: list = None
    kwargs: dict = None

    def __post_init__(self):
        if self.args is None:
            self.args = []
        if self.kwargs is None:
            self.kwargs = {}
    
    @classmethod
    def get_call_type(cls):
        return "api_request"

def api_function(name=None):
    def decorator(func):
        """Decorator to register a function as an API method"""
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        wrapper.api_method = True
        wrapper.api_name = name or func.__name__
        return wrapper
    return decorator

def remote_call_handler(remote_class):
    call_type = remote_class.get_call_type()
    def decorator(func):
        def wrapper(self, remote_call: RemoteCall):
            if remote_call.call_type != call_type:
                raise ValueError(f"Expected call type '{call_type}', got '{remote_call.call_type}'")
            return func(self, remote_class(**remote_call.call_data))
        wrapper.remote_call = True
        wrapper.remote_call_type = call_type
        wrapper.remote_call_class = remote_class
        return wrapper
    return decorator

class RemoteObjectServer(MessageProcessor):
    def __init__(self):
        super().__init__("remote_call")
        self.executer: ThreadPoolExecutor = ThreadPoolExecutor(max_workers=4)
        self._methods: Dict[str, callable] = {}
        self._objects: Dict[str, object] = {}
        self._classes: Dict[str, List[str]] = {}
        self._handlers: Dict[str, callable] = {}

        # Discover decorated methods
        for name in dir(self):
            attr = getattr(self, name)

            # API Methods
            if callable(attr) and hasattr(attr, 'api_method'):
                self.register_method(attr.api_name, attr)
            
            # Remote call handlers
            if callable(attr) and hasattr(attr, 'remote_call'):
                self.register_handler(attr.remote_call_type, attr)
    
    def register_handler(self, call_type: str, handler: callable):
        """Register a handler for a specific remote call type"""
        if call_type not in self._handlers:
            self._handlers[call_type] = handler

    def register_method(self, method_name: str, func: callable):
        """Register a method that can be called remotely"""
        self._methods[method_name] = func

    def register_object(self, obj: object):
        """Register an object that can be called remotely"""
        obj_id = str(id(obj))
        self._objects[obj_id] = obj
        self._classes.setdefault(obj.__class__.__name__, []).append(obj_id)
        return obj_id

    def unregister_object(self, obj):
        """Unregister a remote object"""
        obj_id = str(id(obj))
        if obj_id in self._objects:
            del self._objects[obj_id]
            class_obj_list = self._classes.get(obj.__class__.__name__, [])
            if obj_id in class_obj_list:
                class_obj_list.remove(obj_id)

    @remote_call_handler(APIRequest)
    def api_request_handler(self, request: APIRequest):
        method = request.func_name

        if method in self._methods:
            return self._methods[method](*request.args, **request.kwargs)
        else:
            raise Exception(f"API Method '{method}' not found")
    
    @remote_call_handler(RemoteObjectCall)
    def handle_remote_object_call(self, remote_call: RemoteObjectCall):
        obj_id = remote_call.obj_id
        args = remote_call.args
        kwargs = remote_call.kwargs

        if obj_id not in self._objects:
            raise Exception(f"Remote object '{obj_id}' not found")

        obj = self._objects[obj_id]
        method = getattr(obj, remote_call.attr_name)
        return method(*args, **kwargs)

    @remote_call_handler(RemoteObjectGet)
    def handle_remote_object_get(self, remote_call: RemoteObjectGet):
        obj_id = remote_call.obj_id

        if obj_id not in self._objects:
            raise Exception(f"Remote object '{obj_id}' not found")

        obj = self._objects[obj_id]
        return getattr(obj, remote_call.attr_name)
    
    @remote_call_handler(RemoteObjectSet)
    def handle_remote_object_set(self, remote_call: RemoteObjectSet):
        obj_id = remote_call.obj_id
        value = remote_call.value

        if obj_id not in self._objects:
            raise Exception(f"Remote object '{obj_id}' not found")

        obj = self._objects[obj_id]
        setattr(obj, remote_call.attr_name, value)

    def process_message(self, message, client_socket: socket.socket, address: tuple):
        remote_call = RemoteCall.from_message(message)
        
        if remote_call.call_type in self._handlers:
            try:
                result = self._handlers[remote_call.call_type](remote_call)
                response = remote_call.create_response(result=result)
            except Exception as e:
                response = remote_call.create_response(error=str(e))
        else:
            response = remote_call.create_response(error=f"Unknown call type: {remote_call.call_type}")
        
        self.server.send_message(response.to_message(), address)
    
    @api_function(name='list_objects')
    def list_objects(self, class_name: str) -> List[str]:
        """List all registered remote objects of a specific class"""
        return self._classes.get(class_name, [])

    def handle_api_request(self, request: APIRequest, client_socket: socket.socket, address: tuple):
        """Handle API requests from clients"""
        method = request.method

        if method in self._methods:
            func = self._methods[method]
            try:
                result = func(*request.args, **request.kwargs)
                response = request.create_response(result=result)
                self.send_message(response.to_message(), address)
            except Exception as e:
                response = request.create_response(error=str(e))
                self.send_message(response.to_message(), address)
        else:
            response = request.create_response(error=f"Method '{method}' not found")
            self.send_message(response.to_message(), address)

class ClientProcessor(MessageProcessor):
    def __init__(self):
        super().__init__("remote_call")
        self.request_id = get_request_id()
        self.future_map = {}
        self._executor = ThreadPoolExecutor(max_workers=4)
    
    def process_message(self, message, sock: socket.socket, address: tuple):
        remote_call = RemoteCall.from_message(message)

        if not remote_call.is_response:
            raise Exception("Received non-response message in ClientProcessor")
        
        message_id = remote_call.message_id

        if message_id in self.future_map:
            future = self.future_map[message_id]
            del self.future_map[message_id]
            future.set_result(remote_call.result)
        else:
            print(f"❌ No future found for message ID: {message_id}")

    def send_remote_call(self, request: RemoteCallBase):
        remote_call = request.to_remote_call()
        future = Future()
        self.future_map[remote_call.message_id] = future
        self._executor.submit(self._send_remote_call, remote_call, future)
        return future

    def async_call(self, method, args=None, kwargs=None):
        """Call a remote API method"""
        if args is None:
            args = []
        if kwargs is None:
            kwargs = {}

        request = APIRequest(func_name=method, args=args, kwargs=kwargs)
        remote_call = request.to_remote_call()

        future = Future()
        self.future_map[remote_call.message_id] = future
        self._executor.submit(self._send_remote_call, remote_call, future)

        return future
    
    def call(self, method, args=None, kwargs=None, timeout=30):
        future = self.async_call(method, args, kwargs)
        try:
            return future.result(timeout=timeout)
        except Exception as e:
            print(f"❌ Error calling remote method '{method}': {e}")
            raise e

    def _send_remote_call(self, request: RemoteCall, future: Future):
        """Send a remote call to the server"""
        try:
            message = request.to_message()
            self.server.send_message(message)
            # print(f"📤 Sent remote call: {request.attr_name} with ID {request.message_id}")
        except Exception as e:
            future.set_exception(e)
            print(f"❌ Failed to send remote call: {e}")
            release_request_id(request.message_id)


class RemoteCallableAttribute:
    """Represents a remote attribute that can be called as a method or accessed as a property"""
    
    def __init__(self, remote_obj: RemoteObject, name: str):
        self._remote_obj = remote_obj
        self._name = name


    def __call__(self, *args, **kwds):
        remote_call = RemoteObjectCall(
            obj_id=self._remote_obj._obj_id,
            attr_name=self._name,
            args=list(args),
            kwargs=kwds
        )
        future = self._remote_obj._client.send_remote_call(remote_call)
        return future.result(timeout=30)


class RemoteObject:
    """Proxy object that forwards method calls and property access to a remote object"""
    
    def __init__(self, obj_id: str, client: ClientProcessor, original_class: type = None):
        self._client: ClientProcessor = client
        self._obj_id: str = obj_id
        self._original_class: type = original_class
        self._callables = dict()
        
        # Create remote attributes for all eligible attributes
        for attr in dir(original_class):
            if not attr.startswith('_'):
                if callable(getattr(original_class, attr)):
                    self._callables[attr] = RemoteCallableAttribute(self, attr)
    
    def __getattribute__(self, name):
        if name.startswith('_'):
            return super().__getattribute__(name)
        
        if attr := self._callables.get(name, None):
            return attr

        remote_get = RemoteObjectGet(
            self._obj_id,
            name
        )
        future = self._client.send_remote_call(remote_get)
        return future.result(timeout=30)

    def __setattr__(self, name, value):
        if name.startswith('_'):
            super().__setattr__(name, value)
            return

        remote_set = RemoteObjectSet(
            self._obj_id,
            name,
            value
        )
        future = self._client.send_remote_call(remote_set)
        return future.result(timeout=30)
