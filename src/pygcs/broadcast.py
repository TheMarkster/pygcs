from __future__ import annotations
from typing import Union
import threading

if 'BROADCAST_MODULE' in globals():
    raise Exception("broadcast.py loaded multiple times!")
else:
    BROADCAST_MODULE = True

class Broadcast:
    def __init__(self):
        self.instances = {} # class.name -> List[instance]
        self.consumers = {} # signal -> List[Tuple[func, class]]
        self.direct_consumers = {} # signal -> List[callback] (for direct connections)
        self.forwarding = [] # Send a copy of all signals here
        self.event_history = []  # For debugging/replay
        self.middleware = []     # For event processing pipeline
        self.namespaces = {}     # For addon isolation
    
    def forward_to(self, gateway_func):
        """Add a gateway function to forward all events to"""
        self.forwarding.append(gateway_func)
    
    def emit(self, signal, *args, namespace=None, **kwargs):
        # Add middleware support
        event_data = {'signal': signal, 'args': args, 'kwargs': kwargs, 'namespace': namespace}
        
        for middleware in self.middleware:
            event_data = middleware(event_data)
            if event_data is None:  # Middleware can cancel events
                return
        
        # Log for debugging
        self.event_history.append(event_data)
        
        # Emit to appropriate namespace or globally
        target_consumers = self.consumers.get(signal, [])
        if namespace:
            target_consumers = [(f, cls) for f, cls in target_consumers 
                              if self.namespaces.get(cls) == namespace]
        
        for func, cls_name in target_consumers:
            if cls_name is None:
                # Standalone function - call directly
                try:
                    func(*args, **kwargs)
                except Exception as e:
                    # Error handling for robust addon system
                    self.emit('broadcast_error', signal, 'standalone_function', e)
            else:
                # Class method - call on all instances of the class
                for instance in self.instances.get(cls_name, []):
                    # Check inheritance if this method requires it
                    if hasattr(func, '_broadcast_needs_inheritance_check'):
                        if not isinstance(instance, Broadcastable):
                            raise TypeError(
                                f"Class '{cls_name}' must inherit from Broadcastable to use @broadcast.consumer. "
                                f"Make sure {cls_name} extends Broadcastable."
                            )
                        # Remove the check flag after first validation
                        delattr(func, '_broadcast_needs_inheritance_check')
                    
                    try:
                        func(instance, *args, **kwargs)
                    except Exception as e:
                        # Error handling for robust addon system
                        self.emit('broadcast_error', signal, cls_name, e)
        
        # Call direct consumers (from Signal.connect())
        for callback in self.direct_consumers.get(signal, []):
            try:
                callback(*args, **kwargs)
            except Exception as e:
                self.emit('direct_consumer_error', signal, callback, e)
        
        for gateway in self.forwarding:
            try:
                gateway(signal, *args, **kwargs)
            except Exception as e:
                # Don't let watcher errors break the broadcast
                self.emit('forwarding_error', signal, gateway, e)

    def consumer(self, signal: Union[str, Signal]):
        """Decorator to register a method as a consumer for a signal"""
        if hasattr(signal, "name"):
            signal = signal.name

        def decorator(func):
            # Check if this is a class method or a standalone function
            qualname_parts = func.__qualname__.split(".")
            is_class_method = len(qualname_parts) > 1
            
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
        if namespace:
            self.namespaces[cls_name] = namespace
        
        # Emit registration event
        self.emit('instance_registered', instance, namespace=namespace)
    
    def unregister_instance(self, instance):
        """Unregister an instance from receiving broadcasts"""
        cls_name = instance.__class__.__name__
        instances_list = self.instances.get(cls_name, [])
        if instance in instances_list:
            instances_list.remove(instance)
            # Clean up empty lists
            if not instances_list:
                del self.instances[cls_name]
                # Clean up namespace if this was the last instance
                if cls_name in self.namespaces:
                    del self.namespaces[cls_name]
        
        # Emit unregistration event
        self.emit('instance_unregistered', instance)
    
    def add_middleware(self, middleware_func):
        """Add middleware for event processing pipeline"""
        self.middleware.append(middleware_func)
    
    def add_watcher(self, watcher_func):
        """Add a watcher that receives all broadcast signals"""
        self.forwarding.append(watcher_func)
    
    def remove_watcher(self, watcher_func):
        """Remove a watcher"""
        if watcher_func in self.forwarding:
            self.forwarding.remove(watcher_func)
    
    def get_event_history(self, signal=None, limit=None):
        """Get event history, optionally filtered by signal"""
        history = self.event_history
        if signal:
            history = [event for event in history if event['signal'] == signal]
        if limit:
            history = history[-limit:]
        return history
    
    def clear_history(self):
        """Clear the event history"""
        self.event_history.clear()
    
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

    def emitter(self, signal: str, include_return=True):
        """Decorator that broadcasts the return value of a function"""
        def decorator(func):
            def wrapper(*args, **kwargs):
                try:
                    result = func(*args, **kwargs)
                    if include_return:
                        # Emit signal with function result
                        self.emit(signal, result, *args, **kwargs)
                    else:
                        # Emit signal without return value, just function args
                        self.emit(signal, *args, **kwargs)
                    return result
                except Exception as e:
                    # Emit error signal if function fails
                    self.emit(f"{signal}_error", e, *args, **kwargs)
                    raise
            
            # Preserve function metadata
            wrapper.__name__ = func.__name__
            wrapper.__doc__ = func.__doc__
            wrapper.__qualname__ = func.__qualname__
            return wrapper
        return decorator

    def add_direct_consumer(self, signal, callback):
        """Add a direct consumer callback for a signal"""
        self.direct_consumers.setdefault(signal, []).append(callback)
    
    def remove_direct_consumer(self, signal, callback):
        """Remove a direct consumer callback from a signal"""
        consumers = self.direct_consumers.get(signal, [])
        if callback in consumers:
            consumers.remove(callback)
            if not consumers:  # Clean up empty lists
                del self.direct_consumers[signal]

class Broadcastable:
    def __init__(self, namespace=None):
        self._broadcast_namespace = namespace
        get_broadcast().register_instance(self, namespace)
    
    def __del__(self):
        get_broadcast().unregister_instance(self)

class Signal:
    """A signal that can be defined as a class attribute and automatically routes to broadcast"""
    def __init__(self, name=None, global_signal=True):
        self.name = name
        self.global_signal = global_signal
        self._owner_class = None
    
    def __set_name__(self, owner, name):
        """Called when the signal is assigned as a class attribute"""
        if self.name is None:
            self.name = name
        self._owner_class = owner.__name__
    
    def __get__(self, instance, owner):
        """Return a bound signal when accessed from an instance"""
        if instance is None:
            return self
        return BoundSignal(self, instance)

    def emit(self, *args, **kwargs):
        """Emit this signal through the global broadcast system"""
        get_broadcast().emit(self.name, *args, namespace=None, **kwargs)

class BoundSignal:
    """A signal bound to a specific instance"""
    def __init__(self, signal, instance):
        self.signal = signal
        self.instance = instance
        
        # Use global signal name by default, or class-specific if explicitly requested
        if getattr(signal, 'global_signal', True):
            self.name = signal.name
        else:
            self.name = f"{signal._owner_class}.{signal.name}"
    
    def emit(self, *args, **kwargs):
        """Emit this signal through the global broadcast system"""
        namespace = getattr(self.instance, '_broadcast_namespace', None)
        get_broadcast().emit(self.name, *args, namespace=namespace, **kwargs)
    
    def connect(self, callback):
        """Connect a callback directly to this signal"""
        get_broadcast().add_direct_consumer(self.name, callback)
    
    def disconnect(self, callback):
        """Disconnect a callback from this signal"""
        get_broadcast().remove_direct_consumer(self.name, callback)

# Module-level singleton implementation
_broadcast_instance = None
_broadcast_lock = None

def _get_lock():
    """Get or create the singleton lock"""
    global _broadcast_lock
    if _broadcast_lock is None:
        _broadcast_lock = threading.Lock()
    return _broadcast_lock

def get_broadcast():
    """Get the global broadcast instance - thread-safe singleton"""
    global _broadcast_instance
    if _broadcast_instance is None:
        lock = _get_lock()
        with lock:
            # Double-check locking pattern
            if _broadcast_instance is None:
                _broadcast_instance = Broadcast()
    return _broadcast_instance

# Convenience reference for backward compatibility
# This will always return the same instance due to the singleton pattern
broadcast = get_broadcast()
