#!/usr/bin/env python3
"""
Test script for the print interceptor
"""

from src.pygcs.print_interceptor import PrintInterceptor, LogEvent, create_console_logger, create_file_logger


def test_basic_interception():
    """Test basic print interception"""
    print("=== Testing Basic Print Interception ===")
    
    def my_log_handler(event: LogEvent):
        print(f"🔍 INTERCEPTED: '{event.message}' from {event.caller_function}() at line {event.caller_line}")
    
    print("Before interception")
    
    with PrintInterceptor(my_log_handler):
        print("This message is intercepted!")
        print("So is this one!")
        
        def nested_function():
            print("Message from nested function")
        
        nested_function()
    
    print("After interception")


def test_event_storage():
    """Test capturing and storing events"""
    print("\n=== Testing Event Storage ===")
    
    interceptor = PrintInterceptor()
    
    with interceptor:
        print("First captured message")
        print("Second captured message") 
        print("Third captured message")
    
    events = interceptor.get_events()
    print(f"Captured {len(events)} events:")
    
    for i, event in enumerate(events, 1):
        print(f"  {i}. [{event.timestamp.strftime('%H:%M:%S.%f')[:-3]}] "
              f"Thread:{event.thread_name} | {event.message}")


def test_console_logger():
    """Test the console logger utility"""
    print("\n=== Testing Console Logger ===")
    
    console_logger = create_console_logger("[MY_APP]")
    
    with PrintInterceptor(console_logger):
        print("Message with custom console logger")
        print("Another message")


def test_file_logger():
    """Test the file logger utility"""
    print("\n=== Testing File Logger ===")
    
    file_logger = create_file_logger("test_print_log.txt")
    
    with PrintInterceptor(file_logger):
        print("This goes to the file")
        print("So does this")
    
    print("Check 'test_print_log.txt' for the logged output")


def test_threading():
    """Test print interception in threaded environment"""
    print("\n=== Testing Threading ===")
    import threading
    import time
    
    def thread_log_handler(event: LogEvent):
        print(f"🧵 [{event.thread_name}] {event.caller_function}(): {event.message}")
    
    def worker_thread(thread_id):
        time.sleep(0.1)  # Small delay to see threading
        print(f"Message from worker thread {thread_id}")
    
    with PrintInterceptor(thread_log_handler):
        print("Main thread message")
        
        # Create some worker threads
        threads = []
        for i in range(3):
            t = threading.Thread(target=worker_thread, args=(i,), name=f"Worker-{i}")
            threads.append(t)
            t.start()
        
        # Wait for threads to complete
        for t in threads:
            t.join()
        
        print("All threads completed")


if __name__ == "__main__":
    test_basic_interception()
    test_event_storage()
    test_console_logger()
    test_file_logger()
    test_threading()
    
    print("\n✅ All tests completed!")
