#!/usr/bin/env python3
"""
Security Example for Remote Objects

This example demonstrates how to properly secure remote objects using the
enhanced security features in the RemoteObjectServer.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../src'))

from pygcs.remote_objects import RemoteObjectServer
from pygcs.networking import Server
import threading
import time

# Example classes to demonstrate security controls
class BankAccount:
    def __init__(self, account_number: str, balance: float):
        self.account_number = account_number
        self.balance = balance
        self._pin = "1234"  # Private attribute - should not be accessible
        
    def deposit(self, amount: float):
        """Public method - should be accessible"""
        if amount > 0:
            self.balance += amount
            return self.balance
        raise ValueError("Amount must be positive")
    
    def withdraw(self, amount: float):
        """Public method - should be accessible"""
        if amount > self.balance:
            raise ValueError("Insufficient funds")
        self.balance -= amount
        return self.balance
    
    def get_balance(self):
        """Public method - should be accessible"""
        return self.balance
    
    def _reset_pin(self, new_pin: str):
        """Private method - should NOT be accessible"""
        self._pin = new_pin
    
    def __del__(self):
        """Dunder method - should NOT be accessible"""
        print("Account deleted")

class PublicCalculator:
    """A simple calculator with some restricted operations"""
    
    def add(self, a: float, b: float) -> float:
        return a + b
    
    def subtract(self, a: float, b: float) -> float:
        return a - b
    
    def multiply(self, a: float, b: float) -> float:
        return a * b
    
    def divide(self, a: float, b: float) -> float:
        if b == 0:
            raise ValueError("Division by zero")
        return a / b
    
    def _dangerous_operation(self):
        """Private method that shouldn't be accessible"""
        exec("print('This should not be accessible!')")

def create_secure_server():
    """Create a properly configured secure remote object server"""
    
    # Create server with security settings
    server = Server("localhost", 8888)
    remote_server = RemoteObjectServer()
    
    # Configure security settings
    remote_server.set_strict_mode(True)  # Only allow explicitly whitelisted attributes
    
    # Add allowed classes
    remote_server.add_allowed_class(['BankAccount', 'PublicCalculator'])
    
    # Define allowed attributes for each class (strict whitelist)
    remote_server.add_allowed_attributes('BankAccount', [
        'account_number', 'balance',  # Properties
        'deposit', 'withdraw', 'get_balance'  # Methods
        # Note: _pin and _reset_pin are NOT included
    ])
    
    remote_server.add_allowed_attributes('PublicCalculator', [
        'add', 'subtract', 'multiply', 'divide'
        # Note: _dangerous_operation is NOT included
    ])
    
    # Add additional globally blocked attributes if needed
    remote_server.add_blocked_attributes([
        'exec', 'eval', '__import__', 'open', 'input'
    ])
    
    # Register objects
    account = BankAccount("123456", 1000.0)
    calculator = PublicCalculator()
    
    account_id = remote_server.register_object(account)
    calc_id = remote_server.register_object(calculator)
    
    print(f"✅ Bank Account registered with ID: {account_id}")
    print(f"✅ Calculator registered with ID: {calc_id}")
    
    # Attach processor to server
    server.add_processor(remote_server)
    
    return server, remote_server, account_id, calc_id

def demonstrate_security_violations():
    """Show how security violations are caught"""
    print("\n🛡️  Security Demonstration")
    print("=" * 50)
    
    # Create a test server
    remote_server = RemoteObjectServer()
    remote_server.set_strict_mode(True)
    remote_server.add_allowed_class('BankAccount')
    remote_server.add_allowed_attributes('BankAccount', ['deposit', 'get_balance'])
    
    account = BankAccount("TEST", 100.0)
    account_id = remote_server.register_object(account)
    
    # Test 1: Accessing private attribute (should fail)
    print("\n🔒 Test 1: Attempting to access private attribute '_pin'")
    try:
        if remote_server._is_attribute_allowed(account, '_pin'):
            print("❌ SECURITY FAIL: Private attribute accessible!")
        else:
            print("✅ SECURITY PASS: Private attribute blocked")
    except Exception as e:
        print(f"✅ SECURITY PASS: Exception raised - {e}")
    
    # Test 2: Accessing dunder method (should fail)
    print("\n🔒 Test 2: Attempting to access dunder method '__class__'")
    try:
        if remote_server._is_attribute_allowed(account, '__class__'):
            print("❌ SECURITY FAIL: Dunder method accessible!")
        else:
            print("✅ SECURITY PASS: Dunder method blocked")
    except Exception as e:
        print(f"✅ SECURITY PASS: Exception raised - {e}")
    
    # Test 3: Accessing non-whitelisted method (should fail)
    print("\n🔒 Test 3: Attempting to access non-whitelisted method 'withdraw'")
    try:
        if remote_server._is_attribute_allowed(account, 'withdraw'):
            print("❌ SECURITY FAIL: Non-whitelisted method accessible!")
        else:
            print("✅ SECURITY PASS: Non-whitelisted method blocked")
    except Exception as e:
        print(f"✅ SECURITY PASS: Exception raised - {e}")
    
    # Test 4: Accessing whitelisted method (should succeed)
    print("\n🔒 Test 4: Attempting to access whitelisted method 'deposit'")
    try:
        if remote_server._is_attribute_allowed(account, 'deposit'):
            print("✅ SECURITY PASS: Whitelisted method accessible")
        else:
            print("❌ SECURITY FAIL: Whitelisted method blocked!")
    except Exception as e:
        print(f"❌ SECURITY FAIL: Exception raised - {e}")

def security_checklist():
    """Print a security checklist for developers"""
    print("\n📋 SECURITY CHECKLIST")
    print("=" * 50)
    print("""
✅ Use strict_mode=True to whitelist only necessary attributes
✅ Explicitly define allowed attributes for each class
✅ Never expose private methods/attributes (starting with _)
✅ Block dangerous built-ins (__import__, exec, eval, etc.)
✅ Validate object types before serialization
✅ Use proper authentication/authorization for network layer
✅ Implement rate limiting to prevent abuse
✅ Log security violations for monitoring
✅ Regularly audit your whitelisted attributes
✅ Consider using read-only proxies when possible

⚠️  ADDITIONAL RECOMMENDATIONS:
- Implement client authentication before allowing any calls
- Use TLS/SSL for network encryption
- Validate all input data types and ranges
- Implement session management and timeouts
- Consider using sandboxed execution environments
- Monitor for unusual activity patterns
- Keep security-sensitive operations on server-side only
    """)

if __name__ == "__main__":
    print("🔐 REMOTE OBJECT SECURITY DEMONSTRATION")
    print("=" * 60)
    
    # Demonstrate security controls
    demonstrate_security_violations()
    
    # Show security checklist
    security_checklist()
    
    print("\n🏁 Security demonstration complete!")
    print("\nTo run a full server example:")
    print("1. Create server with create_secure_server()")
    print("2. Configure authentication in your networking layer")
    print("3. Monitor logs for security violations")
