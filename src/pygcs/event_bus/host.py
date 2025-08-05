from .handler import EventHandler
from typing import Dict, List, Tuple, Union
from .event import Event, broadcast_func, get_metastate
from .runtime import set_event_host, get_event_host
import threading

class EventMetadata:
    def __init__(self, host: EventHandler, metadata: Dict[str, Union[str, List[str]]]):
        self._host = host
        self._metadata = metadata
        self._original_metadata = {}

    @property
    def metadata(self) -> Dict[str, Union[str, List[str]]]:
        """Get the metadata dictionary"""
        return self._metadata
    
    @property
    def original_metadata(self) -> Dict[str, Union[str, List[str]]]:
        """Get the original metadata before any modifications"""
        return self._original_metadata
    
    @property
    def host(self) -> EventHandler:
        """Get the event host"""
        return self._host
    
    def __enter__(self):
        """Enter the context manager, blocking events"""
        self.host.lock.acquire()

        for k, v in self.metadata.items():
            if k in get_metastate():
                self._original_metadata[k] = get_metastate()[k]
            get_metastate()[k] = v

        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Exit the context manager, unblocking events"""
        for k, v in self.metadata.items():
            if k in self.original_metadata:
                self.get_metastate()[k] = self.original_metadata[k]
            else:
                del get_metastate()[k]

        self.host.lock.release()
        return False

class EventHost(EventHandler):
    def __init__(self, name=None):
        if name is None:
            name = f"EventHost-{id(self)}"

        super().__init__(name)
        self.instances: Dict[str, list] = {} # class.name -> List[instance]
        self.consumers: Dict[str, List[Tuple[callable, Union[str, None]]]] = {}
        self.lock: threading.RLock = threading.RLock()

    def process(self, event) -> Event:
        target_consumers = self.consumers.get(event.signal, [])

        # Print the event trace for debugging
        if event._metadata.get('_trace', True) and event._metadata.get('_debug', False):
            with EventMetadata(self, {'_trace': False, '_forward': False}):
                print(f"🔄 Processing event: {event.signal} with {len(target_consumers)} consumers")
                print(f"🔄 Args: {event.args}, Kwargs: {event.kwargs}")
                for arg in event.args:
                    print(f"🔄 Arg: {arg}")

                print("\nTraceback:")
                for dev, path in zip(reversed(event._metadata.get('device', [])), reversed(event._metadata.get('path', []))):
                    print(f"🔄 Device: {dev}")
                    for p in reversed(path):
                        print(f"\t🔄 Path: {p}")
                print("\nMetadata:")
                for k, v in event._metadata.items():
                    print(f"🔄 {k}: {v}")
                print("🔄 End of event trace\n")
        else:
            pass
        
        # Send the event to registered consumers
        for func, cls_name in target_consumers:
            if cls_name is None:
                # Standalone function - call directly
                try:
                    func(*event.args, **event.kwargs)
                except Exception as e:
                    # Error handling for robust addon system
                    self.broadcast('broadcast_error', event.signal, 'standalone_function', e)
            else:
                # Class method - call on all instances of the class
                for instance in self.instances.get(cls_name, []):
                    try:
                        func(instance, *event.args, **event.kwargs)
                    except Exception as e:

                        # Error handling for robust addon system
                        self.broadcast('broadcast_error', event.signal, cls_name, e)

        # Return unmodified event for further processing if needed
        return event

    @broadcast_func
    def broadcast(self, signal, *args, _metadata=None, **kwargs):
        event = Event(signal, args, kwargs, _metadata or {})
        self.receive(event)

    def consumer(self, signal: str):
        """Decorator to register a method as a consumer for a signal"""
        def decorator(func):
            # Check if this is a class method or a standalone function
            qualname_parts = func.__qualname__.split(".")
            is_class_method = len(qualname_parts) > 1 and '<locals>' not in qualname_parts
            
            if is_class_method:
                cls_name = qualname_parts[0]
                
                # For class methods, we'll defer the inheritance check until the method is actually called
                # or we can check it during emit() when we have access to the instance
                
                # Store the original function and mark it as needing inheritance check
                func._broadcast_needs_inheritance_check = True
                func._broadcast_class_name = cls_name
                
                # For class methods, store the class name for instance lookup
                self.consumers.setdefault(signal, []).append((func, cls_name))
            else:
                # For standalone functions, store None as the class name
                self.consumers.setdefault(signal, []).append((func, None))
                
            return func
        return decorator

    def register_instance(self, instance, namespace=None):
        """Register an instance to receive broadcast signals"""
        cls_name = instance.__class__.__name__
        self.instances.setdefault(cls_name, []).append(instance)
        # if namespace:
        #     self.namespaces[cls_name] = namespace
        
        # Emit registration event
        self.broadcast('instance_registered', instance)
    
    def unregister_instance(self, instance):
        """Unregister an instance from receiving broadcasts"""
        cls_name = instance.__class__.__name__
        instances_list = self.instances.get(cls_name, [])
        if instance in instances_list:
            instances_list.remove(instance)
            # Clean up empty lists
            if not instances_list:
                del self.instances[cls_name]
        
        # Emit unregistration event
        self.broadcast('instance_unregistered', instance)
    
    def get_registered_consumers(self, signal=None):
        """Get list of registered consumers, optionally for a specific signal"""
        if signal:
            return self.consumers.get(signal, [])
        return self.consumers.copy()
    
    def get_registered_instances(self, cls_name=None):
        """Get registered instances, optionally for a specific class"""
        if cls_name:
            return self.instances.get(cls_name, [])
        return self.instances.copy()
    
class Broadcastable:
    """Base class for objects that can receive broadcast events"""
    def __init__(self, namespace=None):
        self._broadcast_namespace = namespace
        get_event_host().register_instance(self, namespace)
    
    def __del__(self):
        get_event_host().unregister_instance(self)

events = EventHost()
set_event_host(events)