from __future__ import annotations

from .networking.server_client import Server, Client, NetworkObject
from .networking.processor import MessageProcessor
from .networking.message import Message
from .networking.exceptions import ProcessorError
from dataclasses import dataclass
import socket
import json
import uuid
from typing import Any, Callable, Optional, Dict
from concurrent.futures import Future, ThreadPoolExecutor
import threading

@dataclass
class APICall:
    method: str
    args: tuple
    kwargs: dict
    call_id: str = None
    is_response: bool = False
    error: str = None
    result: Any = None

    def __post_init__(self):
        if self.call_id is None:
            self.call_id = str(uuid.uuid4())

    def serialize(self) -> dict:
        return {
            'method': self.method,
            'args': self.args,
            'kwargs': self.kwargs,
            'call_id': self.call_id,
            'is_response': self.is_response,
            'error': self.error,
            'result': self.result
        }

    @classmethod
    def deserialize(cls, data: dict) -> APICall:
        return cls(
            method=data['method'],
            args=tuple(data['args']),
            kwargs=data['kwargs'],
            call_id=data.get('call_id'),
            is_response=data.get('is_response', False),
            error=data.get('error'),
            result=data.get('result')
        )

    def create_response(self, result: Any = None, error: str = None) -> 'APICall':
        """Create a response to this API call"""
        return APICall(
            method=self.method,
            args=(),
            kwargs={},
            call_id=self.call_id,
            is_response=True,
            error=error,
            result=result
        )

def api_method(method_name: str = None):
    """Decorator to mark methods as API endpoints"""
    def decorator(func):
        func._api_method = method_name or func.__name__
        func._is_api_method = True
        return func
    return decorator

def client_method(func):
    """Decorator to mark methods as client-only"""
    func._client_only = True
    return func

def server_method(func):
    """Decorator to mark methods as server-only"""
    func._server_only = True
    return func

class APIObject(MessageProcessor):
    """
    API object that works as a MessageProcessor attached to Server or Client.
    
    Usage:
        # As server
        server = Server(port=8080)
        api = MyAPI("my_api")
        server.add_processor(api)
        server.connect()
        
        # As client
        client = Client("localhost", 8080)
        api = MyAPI("my_api")
        client.add_processor(api)
        client.connect()
        result = api.call_remote("method_name", arg1, arg2)
    """
    
    def __init__(self, api_name: str):
        super().__init__(api_name)
        self._api_methods: Dict[str, Callable] = {}
        self._pending_calls: Dict[str, Future] = {}
        self._call_lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=10, thread_name_prefix=f"{api_name}-api")
        self._network_object: Optional[NetworkObject] = None
        
        # Discover API methods
        self._discover_api_methods()
    
    def _discover_api_methods(self):
        """Discover all methods marked with @api_method decorator"""
        for attr_name in dir(self):
            attr = getattr(self, attr_name)
            if callable(attr) and hasattr(attr, '_is_api_method'):
                method_name = getattr(attr, '_api_method', attr_name)
                self._api_methods[method_name] = attr
    
    def set_server(self, network_object: NetworkObject):
        """Called by NetworkObject when this processor is added"""
        super().set_server(network_object)
        self._network_object = network_object
    
    def call_remote(self, method: str, *args, timeout: float = 30.0, **kwargs) -> Any:
        """Call a remote API method and wait for response"""
        if self._network_object is None:
            raise RuntimeError("API object not attached to any network object")
        
        # Create API call
        api_call = APICall(method=method, args=args, kwargs=kwargs)
        
        # Create future for response
        future = Future()
        with self._call_lock:
            self._pending_calls[api_call.call_id] = future
        
        try:
            # Send the call
            message = Message(content=self.content_type, data=api_call.serialize())
            self._network_object.send_message(message)
            
            # Wait for response
            result = future.result(timeout=timeout)
            
            # Handle response
            if isinstance(result, APICall):
                if result.error:
                    raise RuntimeError(f"Remote error: {result.error}")
                return result.result
            else:
                raise RuntimeError(f"Invalid response type: {type(result)}")
                
        except Exception as e:
            # Clean up pending call
            with self._call_lock:
                self._pending_calls.pop(api_call.call_id, None)
            raise
    
    def call_remote_async(self, method: str, *args, **kwargs) -> Future:
        """Call a remote API method asynchronously"""
        if self._network_object is None:
            raise RuntimeError("API object not attached to any network object")
        
        # Create API call
        api_call = APICall(method=method, args=args, kwargs=kwargs)
        
        # Create future for response
        future = Future()
        with self._call_lock:
            self._pending_calls[api_call.call_id] = future
        
        # Send the call
        message = Message(content=self.content_type, data=api_call.serialize())
        self._network_object.send_message(message)
        
        return future
    
    def process_message(self, message: Message, client_socket: socket.socket, address: tuple) -> bool:
        """Process incoming API messages"""
        if message.content != self.content_type:
            return False
        
        try:
            api_call = APICall.deserialize(message.data)
            
            if api_call.is_response:
                # Handle response to our call
                self._handle_response(api_call)
            else:
                # Handle incoming method call
                self._handle_method_call(api_call, client_socket, address)
            
            return True
            
        except Exception as e:
            raise ProcessorError(f"Failed to process API message: {e}") from e
    
    def _handle_response(self, response: APICall):
        """Handle response to a remote call"""
        with self._call_lock:
            future = self._pending_calls.pop(response.call_id, None)
        
        if future and not future.cancelled():
            future.set_result(response)
    
    def _handle_method_call(self, api_call: APICall, client_socket: socket.socket, address: tuple):
        """Handle incoming method call"""
        method_name = api_call.method
        
        if method_name not in self._api_methods:
            # Send error response
            error_response = api_call.create_response(error=f"Unknown method: {method_name}")
            self._send_response(error_response, client_socket)
            return
        
        method = self._api_methods[method_name]
        
        # Check if method is allowed in current mode
        is_server = isinstance(self._network_object, Server)
        
        if is_server and hasattr(method, '_client_only'):
            error_response = api_call.create_response(error=f"Method {method_name} is client-only")
            self._send_response(error_response, client_socket)
            return
        
        if not is_server and hasattr(method, '_server_only'):
            error_response = api_call.create_response(error=f"Method {method_name} is server-only")
            self._send_response(error_response, client_socket)
            return
        
        # Execute method asynchronously
        def execute_method():
            try:
                result = method(*api_call.args, **api_call.kwargs)
                response = api_call.create_response(result=result)
                self._send_response(response, client_socket)
            except Exception as e:
                error_response = api_call.create_response(error=str(e))
                self._send_response(error_response, client_socket)
        
        self._executor.submit(execute_method)
    
    def _send_response(self, response: APICall, client_socket: socket.socket):
        """Send response back to caller"""
        try:
            from .networking.io import write_message
            message = Message(content=self.content_type, data=response.serialize())
            write_message(client_socket, message)
        except Exception:
            # Failed to send response - connection might be closed
            pass
    
    @property
    def is_server(self) -> bool:
        """Check if this API is attached to a server"""
        return isinstance(self._network_object, Server)
    
    @property
    def is_client(self) -> bool:
        """Check if this API is attached to a client"""
        return isinstance(self._network_object, Client)
    
    @property
    def is_connected(self) -> bool:
        """Check if the underlying network object is connected"""
        if self._network_object is None:
            return False
        
        if isinstance(self._network_object, Server):
            return self._network_object.running
        elif isinstance(self._network_object, Client):
            return self._network_object.running
        
        return False
    
    def disconnect(self):
        """Disconnect the underlying network object"""
        if self._network_object:
            self._network_object.stop()
        
        # Cancel pending calls
        with self._call_lock:
            for future in self._pending_calls.values():
                future.cancel()
            self._pending_calls.clear()
    
    def __del__(self):
        """Cleanup when object is destroyed"""
        try:
            # Cancel pending calls
            with self._call_lock:
                for future in self._pending_calls.values():
                    future.cancel()
                self._pending_calls.clear()
            
            self._executor.shutdown(wait=False)
        except:
            pass

class RemoteObject(APIObject):
    def __init__(self, api: APIProcessor, obj_id: str, original_class: type):
        self._api = api
        self._obj_id = obj_id
        self._original_class = original_class
        self._cached_methods = set()
        
        # Discover and wrap methods from the original class
        self._wrap_methods()
    
    def _wrap_methods(self):
        """Dynamically create proxy methods for all public methods of the original class"""
        for attr_name in dir(self._original_class):
            if not attr_name.startswith('_'):
                attr = getattr(self._original_class, attr_name)
                if callable(attr):
                    self._cached_methods.add(attr_name)
                    setattr(self, attr_name, self._create_proxy_method(attr_name))
    
    def _create_proxy_method(self, method_name: str):
        """Create a proxy method that forwards calls to the remote object"""
        def proxy_method(*args, **kwargs):
            return self._api.send_request(
                'call_method', 
                self._obj_id, 
                method_name, 
                args, 
                kwargs,
                timeout=30
            )
        
        proxy_method.__name__ = method_name
        return proxy_method
    
    def __getattr__(self, name):
        """Handle property access and unknown methods"""
        if name in self._cached_methods:
            return getattr(self, name)
        
        # For properties, make a remote call
        return self._api.send_request('get_property', self._obj_id, name, timeout=5)
    
    def __setattr__(self, name, value):
        """Handle property setting"""
        if name.startswith('_') or name in ['_api', '_obj_id', '_original_class', '_cached_methods']:
            super().__setattr__(name, value)
        else:
            self._api.send_request('set_property', self._obj_id, name, value, timeout=5)