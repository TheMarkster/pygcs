#!/usr/bin/env python3
"""
Security Configuration Helper for Remote Objects

This module provides utilities to help configure remote object security
with best practices and common patterns.
"""

from typing import Dict, Set, List, Union, Any
import inspect
import logging

# Set up security logging
security_logger = logging.getLogger('remote_objects.security')

class SecurityProfile:
    """Predefined security profiles for common use cases"""
    
    @staticmethod
    def minimal() -> Dict[str, Any]:
        """Minimal security - only block the most dangerous attributes"""
        return {
            'strict_mode': False,
            'blocked_attributes': {
                '__class__', '__dict__', '__globals__', '__locals__', '__code__',
                '__import__', '__builtins__', '__subclasshook__', '__reduce__',
                '__reduce_ex__', '__getstate__', '__setstate__', '__new__',
                'exec', 'eval', 'compile', 'open', 'input', '__file__'
            }
        }
    
    @staticmethod
    def standard() -> Dict[str, Any]:
        """Standard security - block private attributes and dangerous methods"""
        profile = SecurityProfile.minimal()
        profile.update({
            'strict_mode': True,
            'block_private': True,
            'max_recursion_depth': 5
        })
        return profile
    
    @staticmethod
    def high_security() -> Dict[str, Any]:
        """High security - very restrictive, explicit whitelist only"""
        profile = SecurityProfile.standard()
        profile.update({
            'strict_mode': True,
            'max_recursion_depth': 3,
            'require_explicit_methods': True,
            'log_all_access': True
        })
        return profile

class SecurityAnalyzer:
    """Analyze classes for potential security issues"""
    
    @staticmethod
    def analyze_class(cls: type) -> Dict[str, List[str]]:
        """Analyze a class and categorize its attributes by security risk"""
        dangerous = []
        private = []
        safe_methods = []
        safe_properties = []
        
        for name in dir(cls):
            attr = getattr(cls, name, None)
            
            # Categorize by name patterns
            if name.startswith('__') and name.endswith('__'):
                dangerous.append(name)
            elif name.startswith('_'):
                private.append(name)
            elif callable(attr):
                if not name.startswith('_'):
                    safe_methods.append(name)
            else:
                if not name.startswith('_'):
                    safe_properties.append(name)
        
        return {
            'dangerous': dangerous,
            'private': private,
            'safe_methods': safe_methods,
            'safe_properties': safe_properties
        }
    
    @staticmethod
    def suggest_whitelist(cls: type, include_properties: bool = True) -> Set[str]:
        """Suggest a safe whitelist for a class"""
        analysis = SecurityAnalyzer.analyze_class(cls)
        whitelist = set(analysis['safe_methods'])
        
        if include_properties:
            whitelist.update(analysis['safe_properties'])
        
        return whitelist
    
    @staticmethod
    def find_risky_methods(cls: type) -> List[str]:
        """Find potentially risky methods in a class"""
        risky_patterns = [
            'exec', 'eval', 'compile', 'open', 'file', 'input', 'raw_input',
            'import', 'reload', 'delattr', 'setattr', 'getattr',
            'system', 'popen', 'spawn', 'call'
        ]
        
        risky_methods = []
        for name in dir(cls):
            if any(pattern in name.lower() for pattern in risky_patterns):
                risky_methods.append(name)
        
        return risky_methods

def configure_security(remote_server, profile_name: str = 'standard', 
                      custom_config: Dict[str, Any] = None):
    """Configure security settings on a RemoteObjectServer"""
    
    # Get the base profile
    if profile_name == 'minimal':
        config = SecurityProfile.minimal()
    elif profile_name == 'standard':
        config = SecurityProfile.standard()
    elif profile_name == 'high_security':
        config = SecurityProfile.high_security()
    else:
        raise ValueError(f"Unknown security profile: {profile_name}")
    
    # Apply custom overrides
    if custom_config:
        config.update(custom_config)
    
    # Configure the server
    if 'strict_mode' in config:
        remote_server.set_strict_mode(config['strict_mode'])
    
    if 'blocked_attributes' in config:
        remote_server.add_blocked_attributes(config['blocked_attributes'])
    
    if 'max_recursion_depth' in config:
        remote_server._max_recursion_depth = config['max_recursion_depth']
    
    security_logger.info(f"Applied security profile: {profile_name}")
    return config

def audit_class_security(cls: type, proposed_whitelist: Set[str] = None) -> Dict[str, Any]:
    """Perform a security audit on a class"""
    analysis = SecurityAnalyzer.analyze_class(cls)
    risky_methods = SecurityAnalyzer.find_risky_methods(cls)
    
    audit_result = {
        'class_name': cls.__name__,
        'total_attributes': len(dir(cls)),
        'dangerous_count': len(analysis['dangerous']),
        'private_count': len(analysis['private']),
        'safe_methods_count': len(analysis['safe_methods']),
        'safe_properties_count': len(analysis['safe_properties']),
        'risky_methods': risky_methods,
        'recommended_whitelist': SecurityAnalyzer.suggest_whitelist(cls),
        'security_score': None
    }
    
    # Calculate security score (0-100, higher is safer)
    total_attrs = audit_result['total_attributes']
    dangerous_ratio = audit_result['dangerous_count'] / total_attrs if total_attrs > 0 else 0
    private_ratio = audit_result['private_count'] / total_attrs if total_attrs > 0 else 0
    
    security_score = max(0, 100 - (dangerous_ratio * 50) - (private_ratio * 20) - (len(risky_methods) * 10))
    audit_result['security_score'] = round(security_score, 2)
    
    # Check if proposed whitelist is safe
    if proposed_whitelist:
        dangerous_in_whitelist = set(analysis['dangerous']).intersection(proposed_whitelist)
        private_in_whitelist = set(analysis['private']).intersection(proposed_whitelist)
        risky_in_whitelist = set(risky_methods).intersection(proposed_whitelist)
        
        audit_result['whitelist_issues'] = {
            'dangerous_exposed': list(dangerous_in_whitelist),
            'private_exposed': list(private_in_whitelist),
            'risky_exposed': list(risky_in_whitelist)
        }
    
    return audit_result

def print_security_report(audit_result: Dict[str, Any]):
    """Print a formatted security audit report"""
    print(f"\n🔍 SECURITY AUDIT REPORT: {audit_result['class_name']}")
    print("=" * 60)
    
    score = audit_result['security_score']
    if score >= 80:
        score_emoji = "🟢"
    elif score >= 60:
        score_emoji = "🟡"
    else:
        score_emoji = "🔴"
    
    print(f"Security Score: {score_emoji} {score}/100")
    print(f"Total Attributes: {audit_result['total_attributes']}")
    print(f"Dangerous Attributes: {audit_result['dangerous_count']}")
    print(f"Private Attributes: {audit_result['private_count']}")
    print(f"Safe Methods: {audit_result['safe_methods_count']}")
    print(f"Safe Properties: {audit_result['safe_properties_count']}")
    
    if audit_result['risky_methods']:
        print(f"\n⚠️  RISKY METHODS FOUND:")
        for method in audit_result['risky_methods']:
            print(f"  - {method}")
    
    print(f"\n✅ RECOMMENDED WHITELIST ({len(audit_result['recommended_whitelist'])} items):")
    for attr in sorted(audit_result['recommended_whitelist']):
        print(f"  - {attr}")
    
    # Check whitelist issues
    if 'whitelist_issues' in audit_result:
        issues = audit_result['whitelist_issues']
        if any(issues.values()):
            print(f"\n🚨 WHITELIST SECURITY ISSUES:")
            if issues['dangerous_exposed']:
                print(f"  Dangerous attributes exposed: {issues['dangerous_exposed']}")
            if issues['private_exposed']:
                print(f"  Private attributes exposed: {issues['private_exposed']}")
            if issues['risky_exposed']:
                print(f"  Risky methods exposed: {issues['risky_exposed']}")
        else:
            print(f"\n✅ WHITELIST IS SECURE")

# Example usage
if __name__ == "__main__":
    # Example class for testing
    class ExampleClass:
        def __init__(self):
            self.public_attr = "safe"
            self._private_attr = "hidden"
            
        def safe_method(self):
            return "This is safe"
        
        def _private_method(self):
            return "This should not be exposed"
        
        def eval_something(self, code):
            """This is risky due to name pattern"""
            return f"Would evaluate: {code}"
    
    # Perform security audit
    audit = audit_class_security(ExampleClass, {'safe_method', 'public_attr'})
    print_security_report(audit)
