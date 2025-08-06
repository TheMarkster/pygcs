from __future__ import annotations
from collections.abc import Iterable

from pygcs.networking import Client, Server, MessageProcessor, Message
from dataclasses import dataclass
import socket
from concurrent.futures import Future, ThreadPoolExecutor
import threading
from typing import Dict, List, Literal, Any, Union
from functools import wraps
import weakref
import uuid

@dataclass
class RemoteCall:
    """Base class for remote calls with unified ID management using UUID4"""
    is_response: bool = False
    result: any = None
    error: str = None
    message_id: str = None
    call_type: str = None  # 'method', 'property_get', 'property_set'
    call_data: dict = None

    def __post_init__(self):
        if self.message_id is None:
            self.message_id = self._generate_id()
    
    @classmethod
    def _generate_id(cls) -> str:
        """Generate a unique ID using UUID4 for better entropy and thread safety"""
        return str(uuid.uuid4())

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
        self._volatile_objects: Dict[str, object] = {}
        self._classes: Dict[str, List[str]] = {}
        self._handlers: Dict[str, callable] = {}
        self._allowed_classes: List[str] = []
        
        # Security controls
        self._allowed_attributes: Dict[str, set] = {}  # class_name -> {allowed_attrs}
        self._blocked_attributes: set = {
            '__class__', '__dict__', '__globals__', '__locals__', '__code__',
            '__import__', '__builtins__', '__subclasshook__', '__reduce__',
            '__reduce_ex__', '__getstate__', '__setstate__', '__new__'
        }
        self._max_recursion_depth: int = 10
        self._enable_strict_mode: bool = True  # Only allow explicitly whitelisted attrs

        # Discover decorated methods
        for name in dir(self):
            attr = getattr(self, name)

            # API Methods
            if callable(attr) and hasattr(attr, 'api_method'):
                self.register_method(attr.api_name, attr)
            
            # Remote call handlers
            if callable(attr) and hasattr(attr, 'remote_call'):
                self.register_handler(attr.remote_call_type, attr)
    
    def add_allowed_class(self, class_name: Union[Union[str, type], Iterable[Union[str, type]]]):
        """Add a class to the list of allowed classes for remote objects"""
        if isinstance(class_name, str):
            self._allowed_classes.append(class_name)
        elif isinstance(class_name, type):
            self._allowed_classes.append(class_name.__name__)
        elif hasattr(class_name, '__iter__'):
            for cls in class_name:
                if isinstance(cls, str):
                    self._allowed_classes.append(cls)
                elif isinstance(cls, type):
                    self._allowed_classes.append(cls.__name__)
                else:
                    raise ValueError("Allowed classes must be strings or types")
        else:
            raise ValueError("Allowed class must be a string, type, or iterable of strings/types")
    
    def register_handler(self, call_type: str, handler: callable):
        """Register a handler for a specific remote call type"""
        if call_type not in self._handlers:
            self._handlers[call_type] = handler

    def register_method(self, method_name: str, func: callable):
        """Register a method that can be called remotely"""
        self._methods[method_name] = func

    def register_object(self, obj: object, volatile: bool = False) -> str:
        """Register an object that can be called remotely"""
        obj_id = str(id(obj))

        if type(obj).__name__ not in self._allowed_classes:
            raise ValueError(f"Class '{type(obj).__name__}' is not allowed for remote objects")
        
        if obj_id in self._objects:
            return obj_id  # Already registered
        
        if obj_id in self._volatile_objects:
            if not volatile:
                del self._volatile_objects[obj_id]
                self._objects[obj_id] = obj
            else:
                return obj_id  # Already registered as volatile
        
        if volatile:
            self._volatile_objects[obj_id] = obj
        else:
            self._objects[obj_id] = obj
        
        self._classes.setdefault(obj.__class__.__name__, []).append(obj_id)
        return obj_id
    
    # def register_callable(self, func: callable, volatile: bool = False) -> str:
    #     """Register an object that can be called remotely"""
    #     obj_id = str(id(func))

    #     if obj_id in self._callables:
    #         return obj_id  # Already registered
        
    #     if obj_id in self._volatile_callables:
    #         if not volatile:
    #             del self._volatile_callables[obj_id]
    #             self._callables[obj_id] = func
    #         else:
    #             return obj_id  # Already registered as volatile

    #     if volatile:
    #         self._volatile_callables[obj_id] = func
    #     else:
    #         self._callables[obj_id] = func

    #     return obj_id
    
    @api_function(name='remote_delete_object')
    def remote_delete_object(self, obj_id: str):
        """If the object is volatile, remove it from the server"""
        obj_id = str(obj_id)
        if obj_id in self._volatile_objects:
            obj = self._volatile_objects[obj_id]
            class_name = obj.__class__.__name__
            del self._volatile_objects[obj_id]
            
            obj_list = self._classes.get(class_name, [])
            if obj_id in obj_list:
                obj_list.remove(obj_id)
                if not obj_list:
                    del self._classes[class_name]
    
    # @api_function(name='remote_delete_function')
    # def remote_delete_function(self, func_id: str):
    #     """If the function is volatile, remove it from the server"""
    #     if func_id in self._volatile_callables:
    #         del self._volatile_callables[func_id]

    def unregister_object(self, obj):
        """Unregister a remote object"""
        obj_id = str(id(obj))
        if obj_id in self._objects:
            del self._objects[obj_id]
        elif obj_id in self._volatile_objects:
            del self._volatile_objects[obj_id]
        else:
            return

        class_obj_list = self._classes.get(obj.__class__.__name__, [])
        if obj_id in class_obj_list:
            class_obj_list.remove(obj_id)

    def unregister_callable(self, func):
        """Unregister a remote callable"""
        func_id = str(id(func))
        if func_id in self._callables:
            del self._callables[func_id]
        elif func_id in self._volatile_callables:
            del self._volatile_callables[func_id]
        else:
            return
    
    def encode_data(self, data: Any):
        """Convert objects to strings and register them with security validation"""
        if isinstance(data, list):
            return [self.encode_data(item) for item in data]
        elif isinstance(data, tuple):
            return tuple(self.encode_data(item) for item in data)
        elif isinstance(data, dict):
            return {k: self.encode_data(v) for k, v in data.items()}
        elif isinstance(data, (int, float, bool, type(None))):
            return data
        elif isinstance(data, str):
            return data.replace("\\", "\\\\")
        else:
            # Security validation before registering object
            try:
                self._validate_object_for_serialization(data)
                obj_id = self.register_object(data, volatile=True)
                return f"\\@{obj_id}"
            except ValueError as e:
                raise ValueError(f"Security validation failed: {e}")
    
    def decode_data(self, data: Any):
        """Convert strings back to objects with security validation"""
        if isinstance(data, list):
            return [self.decode_data(item) for item in data]
        elif isinstance(data, tuple):
            return tuple(self.decode_data(item) for item in data)
        elif isinstance(data, dict):
            return {k: self.decode_data(v) for k, v in data.items()}
        elif isinstance(data, (int, float, bool, type(None))):
            return data
        elif isinstance(data, str):
            if data.startswith("\\@"):
                obj_id = data[2:]
                if obj_id in self._objects:
                    return self._objects[obj_id]
                else:
                    raise ValueError(f"Object ID '{obj_id}' not found")
            else:
                return data.replace("\\\\", "\\")


    @remote_call_handler(APIRequest)
    def api_request_handler(self, request: APIRequest):
        method = request.func_name

        if method in self._methods:
            return self._methods[method](*request.args, **request.kwargs)
        else:
            raise Exception(f"API Method '{method}' not found")
    
    def get_object(self, obj_id: str) -> object:
        """Get a registered object by its ID"""
        obj_id = str(obj_id)

        if obj_id in self._objects:
            return self._objects[obj_id]
        elif obj_id in self._volatile_objects:
            return self._volatile_objects[obj_id]
        else:
            raise ValueError(f"Object ID '{obj_id}' not found")

    @remote_call_handler(RemoteObjectCall)
    def handle_remote_object_call(self, remote_call: RemoteObjectCall):
        obj_id = remote_call.obj_id
        attr_name = remote_call.attr_name
        args = self.decode_data(remote_call.args)
        kwargs = self.decode_data(remote_call.kwargs)

        obj = self.get_object(obj_id)
        
        # Security validation: Check if method access is allowed
        if not self._is_attribute_allowed(obj, attr_name):
            raise ValueError(f"Access to attribute '{attr_name}' is not allowed for class '{obj.__class__.__name__}'")
        
        # Additional security: Ensure the attribute is callable
        if not hasattr(obj, attr_name):
            raise ValueError(f"Object does not have attribute '{attr_name}'")
        
        method = getattr(obj, attr_name)
        if not callable(method):
            raise ValueError(f"Attribute '{attr_name}' is not callable")
        
        return self.encode_data(method(*args, **kwargs))

    @remote_call_handler(RemoteObjectGet)
    def handle_remote_object_get(self, remote_call: RemoteObjectGet):
        obj_id = remote_call.obj_id
        attr_name = remote_call.attr_name

        obj = self.get_object(obj_id)
        
        # Security validation: Check if attribute access is allowed
        if not self._is_attribute_allowed(obj, attr_name):
            raise ValueError(f"Access to attribute '{attr_name}' is not allowed for class '{obj.__class__.__name__}'")
        
        if not hasattr(obj, attr_name):
            raise ValueError(f"Object does not have attribute '{attr_name}'")

        return self.encode_data(getattr(obj, attr_name))
    
    @remote_call_handler(RemoteObjectSet)
    def handle_remote_object_set(self, remote_call: RemoteObjectSet):
        obj_id = remote_call.obj_id
        attr_name = remote_call.attr_name
        value = self.decode_data(remote_call.value)

        obj = self.get_object(obj_id)
        
        # Security validation: Check if attribute modification is allowed
        if not self._is_attribute_allowed(obj, attr_name):
            raise ValueError(f"Modification of attribute '{attr_name}' is not allowed for class '{obj.__class__.__name__}'")
        
        if not hasattr(obj, attr_name):
            raise ValueError(f"Object does not have attribute '{attr_name}'")

        setattr(obj, attr_name, value)

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
        return True  # Indicate message was processed successfully
    
    @api_function(name='list_objects')
    def list_objects(self, class_name: str) -> List[str]:
        """List all registered remote objects of a specific class"""
        return self._classes.get(class_name, [])
    
    @api_function(name='list_callables')
    def list_callables(self, obj_id: str) -> List[str]:
        """List all registered remote callables"""
        obj = self.get_object(obj_id)

        callable_attributes = []
        for attr_name in dir(obj):
            if self._is_attribute_allowed(obj, attr_name):
                if callable(getattr(obj, attr_name)):
                    callable_attributes.append(attr_name)
        
        return callable_attributes

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

    def set_strict_mode(self, enabled: bool):
        """Enable/disable strict mode. When enabled, only explicitly allowed attributes are accessible."""
        self._enable_strict_mode = enabled
    
    def add_allowed_attributes(self, class_name: str, attributes: Union[str, Iterable[str]]):
        """Add allowed attributes for a specific class"""
        if isinstance(attributes, str):
            attributes = [attributes]
        
        if class_name not in self._allowed_attributes:
            self._allowed_attributes[class_name] = set()
        
        self._allowed_attributes[class_name].update(attributes)
    
    def add_blocked_attributes(self, attributes: Union[str, Iterable[str]]):
        """Add globally blocked attributes"""
        if isinstance(attributes, str):
            attributes = [attributes]
        self._blocked_attributes.update(attributes)
    
    def _is_attribute_allowed(self, obj: object, attr_name: str) -> bool:
        """Check if attribute access is allowed for the given object"""
        # Always block dangerous attributes
        if attr_name in self._blocked_attributes:
            return False
        
        # Block private attributes by default
        if attr_name.startswith('_'):
            return False
        
        class_name = obj.__class__.__name__
        
        # In strict mode, only explicitly allowed attributes are permitted
        if self._enable_strict_mode:
            allowed_attrs = self._allowed_attributes.get(class_name, set())
            return attr_name in allowed_attrs
        
        # In non-strict mode, allow all non-private, non-blocked attributes
        return True
    
    def _validate_object_for_serialization(self, obj: object, depth: int = 0) -> bool:
        """Validate if an object can be safely serialized and sent over network"""
        if depth > self._max_recursion_depth:
            raise ValueError(f"Object serialization depth exceeded maximum ({self._max_recursion_depth})")
        
        # Allow primitive types
        if isinstance(obj, (int, float, bool, str, type(None))):
            return True
        
        # Allow collections of safe objects
        if isinstance(obj, (list, tuple)):
            return all(self._validate_object_for_serialization(item, depth + 1) for item in obj)
        
        if isinstance(obj, dict):
            return all(
                isinstance(k, str) and self._validate_object_for_serialization(v, depth + 1) 
                for k, v in obj.items()
            )
        
        # For other objects, they must be from allowed classes
        class_name = obj.__class__.__name__
        if class_name not in self._allowed_classes:
            raise ValueError(f"Object of type '{class_name}' is not allowed for remote serialization")
        
        return True

class ClientProcessor(MessageProcessor):
    def __init__(self):
        super().__init__("remote_call")
        self.future_map = {}
        self._executor = ThreadPoolExecutor(max_workers=4)
        self._remote_objects: Dict[str, weakref.ref] = {}

    def encode_data(self, data: Any):
        if isinstance(data, list):
            return [self.encode_data(item) for item in data]
        elif isinstance(data, tuple):
            return tuple(self.encode_data(item) for item in data)
        elif isinstance(data, dict):
            return {k: self.encode_data(v) for k, v in data.items()}
        elif isinstance(data, str):
            return data.replace("\\", "\\\\")
        elif isinstance(data, RemoteObject):
            return f"\\@{data._obj_id}"
        else:
            return data  # Primitive types are returned as is
    
    def decode_data(self, data: Any):
        if isinstance(data, list):
            return [self.decode_data(item) for item in data]
        elif isinstance(data, tuple):
            return tuple(self.decode_data(item) for item in data)
        elif isinstance(data, dict):
            return {k: self.decode_data(v) for k, v in data.items()}
        elif isinstance(data, str):
            if data.startswith("\\@"):
                return RemoteObject(data[2:], self)
            else:
                return data.replace("\\\\", "\\")
        else:
            return data  # Primitive types are returned as is
    
    def get_remote_object(self, obj_id):
        if obj_id in self._remote_objects:
            return self._remote_objects[obj_id]()
        else:
            remote_obj = RemoteObject(obj_id, self)
            self._remote_objects[obj_id] = weakref.ref(remote_obj)
            return remote_obj
    
    def remove_remote_object(self, obj_id):
        if obj_id in self._remote_objects:
            del self._remote_objects[obj_id]
            self.async_call("remote_delete_object", args=obj_id)

    def process_message(self, message, sock: socket.socket, address: tuple):
        try:
            remote_call = RemoteCall.from_message(message)

            if not remote_call.is_response:
                print(f"❌ Received non-response message in ClientProcessor: {remote_call.call_type}")
                return False
            
            
            message_id = remote_call.message_id

            if message_id in self.future_map:
                future = self.future_map[message_id]
                del self.future_map[message_id]
                
                if remote_call.is_error():
                    future.set_exception(Exception(remote_call.error))
                else:
                    decoded_result = self.decode_data(remote_call.result)
                    future.set_result(decoded_result)
                    
                # Note: With UUID4, no ID cleanup needed
            else:
                print(f"❌ No future found for message ID: {message_id}")
            
            return True
            
        except Exception as e:
            print(f"❌ Error processing response: {e}")
            return False

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
            # Note: With UUID4, no ID cleanup needed


class RemoteCallableAttribute:
    """Represents a remote attribute that can be called as a method or accessed as a property"""
    
    def __init__(self, remote_obj: RemoteObject, name: str):
        self._remote_obj = remote_obj
        self._name = name

    def __call__(self, *args, **kwargs):
        args = self._remote_obj._client.encode_data(args)
        kwargs = self._remote_obj._client.encode_data(kwargs)
        remote_call = RemoteObjectCall(
            obj_id=self._remote_obj._obj_id,
            attr_name=self._name,
            args=list(args),
            kwargs=kwargs
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
        if original_class:
            for attr in dir(original_class):
                if not attr.startswith('_'):
                    if callable(getattr(original_class, attr)):
                        self._callables[attr] = RemoteCallableAttribute(self, attr)
        else:
            callables = self._client.call("list_callables", args=[self._obj_id])
            for attr in callables:
                self._callables[attr] = RemoteCallableAttribute(self, attr)

    def __del__(self):
        try:
            self._client.remove_remote_object(self._obj_id)
        except Exception as e:
            # TODO: Workaround for when connection is closed
            pass

    def __getattribute__(self, name):
        if name.startswith('_'):
            return super().__getattribute__(name)
        
        if attr := self._callables.get(name, None):
            return attr

        remote_get = RemoteObjectGet(
            obj_id=self._obj_id,
            attr_name=name
        )
        future = self._client.send_remote_call(remote_get)
        return future.result(timeout=30)

    def __setattr__(self, name, value):
        if name.startswith('_'):
            super().__setattr__(name, value)
            return
        
        value = self._client.encode_data(value)

        remote_set = RemoteObjectSet(
            obj_id=self._obj_id,
            attr_name=name,
            value=value
        )
        future = self._client.send_remote_call(remote_set)
        return future.result(timeout=30)
    
    def __call__(self, *args, **kwargs):
        args = self._client.encode_data(args)
        kwargs = self._client.encode_data(kwargs)
        remote_call = RemoteObjectCall(
            obj_id=self._obj_id,
            attr_name='__call__',
            args=list(args),
            kwargs=kwargs
        )
        future = self._client.send_remote_call(remote_call)
        return future.result(timeout=30)
