"""
Advanced example: Distributed File Manager API
Demonstrates more complex usage patterns
"""

from pygcs.api_server import APIObject, api_method, server_method
import os
import json
import time
from pathlib import Path
from typing import List, Dict, Optional

class FileManagerAPI(APIObject):
    """Distributed file manager that can run on multiple machines"""
    
    def __init__(self, base_path: str = "/tmp/filemanager"):
        super().__init__("file_manager")
        self.base_path = Path(base_path)
        self.base_path.mkdir(exist_ok=True)
        print(f"FileManager initialized with base path: {self.base_path}")
    
    @api_method("list_files")
    def list_files(self, path: str = "") -> List[Dict]:
        """List files in a directory"""
        full_path = self.base_path / path
        
        if not full_path.exists():
            raise FileNotFoundError(f"Path does not exist: {path}")
        
        if not full_path.is_dir():
            raise NotADirectoryError(f"Path is not a directory: {path}")
        
        files = []
        for item in full_path.iterdir():
            files.append({
                'name': item.name,
                'path': str(item.relative_to(self.base_path)),
                'is_dir': item.is_dir(),
                'size': item.stat().st_size if item.is_file() else 0,
                'modified': item.stat().st_mtime
            })
        
        return sorted(files, key=lambda x: (not x['is_dir'], x['name']))
    
    @api_method("read_file")
    def read_file(self, file_path: str) -> str:
        """Read contents of a text file"""
        full_path = self.base_path / file_path
        
        if not full_path.exists():
            raise FileNotFoundError(f"File does not exist: {file_path}")
        
        if not full_path.is_file():
            raise IsADirectoryError(f"Path is not a file: {file_path}")
        
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                return f.read()
        except UnicodeDecodeError:
            raise ValueError(f"File is not a text file: {file_path}")
    
    @api_method("write_file")
    @server_method
    def write_file(self, file_path: str, content: str, create_dirs: bool = True) -> bool:
        """Write content to a file (server only for security)"""
        full_path = self.base_path / file_path
        
        if create_dirs:
            full_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return True
    
    @api_method("delete_file")
    @server_method
    def delete_file(self, file_path: str) -> bool:
        """Delete a file (server only for security)"""
        full_path = self.base_path / file_path
        
        if not full_path.exists():
            raise FileNotFoundError(f"File does not exist: {file_path}")
        
        if full_path.is_file():
            full_path.unlink()
        elif full_path.is_dir():
            full_path.rmdir()  # Only remove empty directories
        else:
            raise ValueError(f"Cannot delete: {file_path}")
        
        return True
    
    @api_method("create_directory")
    @server_method
    def create_directory(self, dir_path: str) -> bool:
        """Create a directory (server only)"""
        full_path = self.base_path / dir_path
        full_path.mkdir(parents=True, exist_ok=True)
        return True
    
    @api_method("get_file_info")
    def get_file_info(self, file_path: str) -> Dict:
        """Get detailed information about a file"""
        full_path = self.base_path / file_path
        
        if not full_path.exists():
            raise FileNotFoundError(f"Path does not exist: {file_path}")
        
        stat = full_path.stat()
        
        return {
            'name': full_path.name,
            'path': str(full_path.relative_to(self.base_path)),
            'absolute_path': str(full_path),
            'is_file': full_path.is_file(),
            'is_dir': full_path.is_dir(),
            'size': stat.st_size,
            'created': stat.st_ctime,
            'modified': stat.st_mtime,
            'accessed': stat.st_atime,
            'permissions': oct(stat.st_mode)[-3:]
        }
    
    @api_method("search_files")
    def search_files(self, pattern: str, path: str = "", recursive: bool = True) -> List[Dict]:
        """Search for files matching a pattern"""
        full_path = self.base_path / path
        
        if not full_path.exists():
            raise FileNotFoundError(f"Path does not exist: {path}")
        
        matches = []
        
        if recursive:
            search_pattern = f"**/*{pattern}*"
        else:
            search_pattern = f"*{pattern}*"
        
        for match in full_path.glob(search_pattern):
            try:
                rel_path = match.relative_to(self.base_path)
                matches.append({
                    'name': match.name,
                    'path': str(rel_path),
                    'is_dir': match.is_dir(),
                    'size': match.stat().st_size if match.is_file() else 0
                })
            except (OSError, ValueError):
                # Skip files we can't access
                continue
        
        return matches

class DistributedFileManager:
    """
    Manager that coordinates multiple FileManager instances
    """
    
    def __init__(self):
        self.servers = {}  # server_name -> FileManagerAPI client
    
    def add_server(self, name: str, host: str, port: int) -> bool:
        """Add a file server to the distributed system"""
        try:
            client = FileManagerAPI()
            client.connect_to_server(host, port)
            self.servers[name] = client
            print(f"✅ Connected to server '{name}' at {host}:{port}")
            return True
        except Exception as e:
            print(f"❌ Failed to connect to server '{name}': {e}")
            return False
    
    def remove_server(self, name: str):
        """Remove a server from the distributed system"""
        if name in self.servers:
            self.servers[name].disconnect()
            del self.servers[name]
            print(f"Disconnected from server '{name}'")
    
    def list_all_files(self, path: str = "") -> Dict[str, List]:
        """List files from all connected servers"""
        all_files = {}
        
        for server_name, client in self.servers.items():
            try:
                files = client.call_remote("list_files", path, timeout=10.0)
                all_files[server_name] = files
            except Exception as e:
                print(f"❌ Error listing files from {server_name}: {e}")
                all_files[server_name] = []
        
        return all_files
    
    def search_all_servers(self, pattern: str) -> Dict[str, List]:
        """Search for files across all servers"""
        results = {}
        
        for server_name, client in self.servers.items():
            try:
                matches = client.call_remote("search_files", pattern, "", True, timeout=30.0)
                results[server_name] = matches
            except Exception as e:
                print(f"❌ Error searching {server_name}: {e}")
                results[server_name] = []
        
        return results
    
    def replicate_file(self, file_path: str, from_server: str, to_servers: List[str]) -> Dict[str, bool]:
        """Replicate a file from one server to others"""
        results = {}
        
        # Read file from source server
        try:
            source_client = self.servers[from_server]
            content = source_client.call_remote("read_file", file_path, timeout=60.0)
        except Exception as e:
            print(f"❌ Failed to read file from {from_server}: {e}")
            return {server: False for server in to_servers}
        
        # Write to target servers
        for server_name in to_servers:
            if server_name not in self.servers:
                results[server_name] = False
                continue
                
            try:
                client = self.servers[server_name]
                success = client.call_remote("write_file", file_path, content, True, timeout=60.0)
                results[server_name] = success
            except Exception as e:
                print(f"❌ Failed to replicate to {server_name}: {e}")
                results[server_name] = False
        
        return results
    
    def disconnect_all(self):
        """Disconnect from all servers"""
        for name in list(self.servers.keys()):
            self.remove_server(name)

# Example usage
if __name__ == "__main__":
    import sys
    import threading
    
    def run_file_server(port: int):
        """Run a file manager server"""
        print(f"=== Starting File Manager Server on port {port} ===")
        
        server = FileManagerAPI(f"/tmp/fileserver_{port}")
        
        try:
            server.start_server('localhost', port)
            print(f"✅ File server started on port {port}")
            
            # Create some test files
            server.write_file("test.txt", "Hello from file server!")
            server.write_file("data/config.json", json.dumps({"port": port, "type": "file_server"}))
            server.create_directory("uploads")
            
            print("Server running... Press Ctrl+C to stop")
            while True:
                time.sleep(1)
                
        except KeyboardInterrupt:
            print(f"\n🛑 Stopping server on port {port}...")
        except Exception as e:
            print(f"❌ Server error: {e}")
        finally:
            server.disconnect()
    
    def run_distributed_client():
        """Run the distributed file manager client"""
        print("=== Starting Distributed File Manager Client ===")
        
        manager = DistributedFileManager()
        
        try:
            # Connect to multiple servers
            manager.add_server("server1", "localhost", 8881)
            manager.add_server("server2", "localhost", 8882)
            
            time.sleep(1)  # Give servers time to start
            
            # List files from all servers
            print("\n--- Files on all servers ---")
            all_files = manager.list_all_files()
            for server, files in all_files.items():
                print(f"\n{server}:")
                for file in files:
                    print(f"  {file['name']} ({'dir' if file['is_dir'] else f'{file['size']} bytes'})")
            
            # Search across all servers
            print("\n--- Searching for 'test' across all servers ---")
            search_results = manager.search_all_servers("test")
            for server, matches in search_results.items():
                print(f"\n{server}: {len(matches)} matches")
                for match in matches:
                    print(f"  {match['path']}")
            
            # Replicate a file
            print("\n--- Replicating test.txt from server1 to server2 ---")
            replication_results = manager.replicate_file("test.txt", "server1", ["server2"])
            for server, success in replication_results.items():
                print(f"  {server}: {'✅ Success' if success else '❌ Failed'}")
            
        except Exception as e:
            print(f"❌ Client error: {e}")
        finally:
            manager.disconnect_all()
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python distributed_api_example.py server1    # Run server on port 8881")
        print("  python distributed_api_example.py server2    # Run server on port 8882")
        print("  python distributed_api_example.py client     # Run distributed client")
        sys.exit(1)
    
    mode = sys.argv[1].lower()
    
    if mode == "server1":
        run_file_server(8881)
    elif mode == "server2":
        run_file_server(8882)
    elif mode == "client":
        run_distributed_client()
    else:
        print(f"Unknown mode: {mode}")
        sys.exit(1)
