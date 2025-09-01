#!/usr/bin/env python3
"""
Multiplayer Stack Startup Script
Starts all necessary components for the multiplayer 24-Game system.
"""

import subprocess
import sys
import os
import time
import signal
import threading
from pathlib import Path
from typing import List, Optional


class MultiplayerStack:
    """Manages the complete multiplayer stack startup and shutdown."""
    
    def __init__(self):
        self.server_process = None
        self.client_processes = []
        self.original_dir = os.getcwd()
        
    def check_dependencies(self) -> bool:
        """Check if all required components exist."""
        print("Checking multiplayer dependencies...")
        
        required_files = [
            "server/start_server.py",
            "server/main.py",
            "server/database/database.py",
            "src/multiplayer_main.py"
        ]
        
        missing_files = []
        for file_path in required_files:
            if not Path(file_path).exists():
                missing_files.append(file_path)
        
        if missing_files:
            print(f"Error: Missing required files: {', '.join(missing_files)}")
            return False
        
        print("All dependencies found")
        return True
    
    def initialize_database(self) -> bool:
        """Initialize the database for multiplayer gaming."""
        print("Initializing database...")
        
        try:
            os.chdir("server")
            
            result = subprocess.run([
                sys.executable, "-c", 
                "from database.database import init_db; init_db(); print('Database initialized successfully')"
            ], check=True, capture_output=True, text=True, timeout=30)
            
            print("Database initialization completed")
            return True
            
        except subprocess.CalledProcessError as e:
            print(f"Database initialization failed: {e.stderr}")
            return False
        except subprocess.TimeoutExpired:
            print("Database initialization timed out")
            return False
        except Exception as e:
            print(f"Database initialization error: {e}")
            return False
        finally:
            os.chdir(self.original_dir)
    
    def start_server(self, background: bool = True) -> bool:
        """Start the multiplayer server."""
        print("Starting multiplayer server...")
        
        try:
            os.chdir("server")
            
            if background:
                self.server_process = subprocess.Popen([
                    sys.executable, "start_server.py"
                ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                
                # Wait for server to start
                time.sleep(3)
                
                # Check if server is running
                if self.server_process.poll() is None:
                    print("Server started successfully in background")
                    print("Server will be accessible at http://localhost:8000")
                    return True
                else:
                    stdout, stderr = self.server_process.communicate()
                    print(f"Server failed to start: {stderr.decode()}")
                    return False
            else:
                # Run server in foreground
                result = subprocess.run([sys.executable, "start_server.py"])
                return result.returncode == 0
                
        except Exception as e:
            print(f"Error starting server: {e}")
            return False
        finally:
            os.chdir(self.original_dir)
    
    def start_client(self, player_name: Optional[str] = None) -> bool:
        """Start a multiplayer client."""
        print(f"Starting multiplayer client{f' for {player_name}' if player_name else ''}...")
        
        try:
            env = os.environ.copy()
            if player_name:
                env["PLAYER_NAME"] = player_name
            
            client_process = subprocess.Popen([
                sys.executable, "src/multiplayer_main.py"
            ], env=env)
            
            self.client_processes.append(client_process)
            print("Client started successfully")
            return True
            
        except Exception as e:
            print(f"Error starting client: {e}")
            return False
    
    def wait_for_server_ready(self, timeout: int = 30) -> bool:
        """Wait for server to be ready to accept connections."""
        print("Waiting for server to be ready...")
        
        import requests
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                response = requests.get("http://localhost:8000/health", timeout=2)
                if response.status_code == 200:
                    print("Server is ready!")
                    return True
            except requests.exceptions.RequestException:
                pass
            
            time.sleep(1)
        
        print("Timeout waiting for server to be ready")
        return False
    
    def stop_all(self):
        """Stop all running processes."""
        print("Stopping multiplayer stack...")
        
        # Stop clients
        for client_process in self.client_processes:
            try:
                client_process.terminate()
                client_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                client_process.kill()
            except Exception as e:
                print(f"Error stopping client: {e}")
        
        # Stop server
        if self.server_process:
            try:
                self.server_process.terminate()
                self.server_process.wait(timeout=10)
                print("Server stopped")
            except subprocess.TimeoutExpired:
                self.server_process.kill()
                print("Server forcefully stopped")
            except Exception as e:
                print(f"Error stopping server: {e}")
    
    def setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""
        def signal_handler(signum, frame):
            print(f"\nReceived signal {signum}, shutting down...")
            self.stop_all()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)


def main():
    """Main entry point for multiplayer stack management."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="24-Game Multiplayer Stack Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/start_multiplayer_stack.py                    # Start server only
  python scripts/start_multiplayer_stack.py --client          # Start server and one client
  python scripts/start_multiplayer_stack.py --clients 2       # Start server and two clients
  python scripts/start_multiplayer_stack.py --server-only     # Start server in foreground
  python scripts/start_multiplayer_stack.py --init-only       # Initialize database only
        """
    )
    
    parser.add_argument("--client", action="store_true", help="Start one client after server")
    parser.add_argument("--clients", type=int, metavar="N", help="Start N clients after server")
    parser.add_argument("--server-only", action="store_true", help="Start server in foreground only")
    parser.add_argument("--init-only", action="store_true", help="Initialize database only")
    parser.add_argument("--no-db-init", action="store_true", help="Skip database initialization")
    parser.add_argument("--wait-for-clients", action="store_true", help="Wait for user input before starting clients")
    
    args = parser.parse_args()
    
    stack = MultiplayerStack()
    stack.setup_signal_handlers()
    
    try:
        # Check dependencies
        if not stack.check_dependencies():
            print("Cannot continue due to missing dependencies")
            sys.exit(1)
        
        # Initialize database
        if not args.no_db_init:
            if not stack.initialize_database():
                print("Database initialization failed")
                sys.exit(1)
        
        # If only initializing database, exit here
        if args.init_only:
            print("Database initialization completed")
            return
        
        # Start server
        server_background = not args.server_only
        if not stack.start_server(background=server_background):
            print("Failed to start server")
            sys.exit(1)
        
        if args.server_only:
            # Server runs in foreground, script ends when server stops
            return
        
        # Wait for server to be ready
        if not stack.wait_for_server_ready():
            print("Server failed to become ready")
            stack.stop_all()
            sys.exit(1)
        
        # Start clients if requested
        num_clients = 0
        if args.client:
            num_clients = 1
        elif args.clients:
            num_clients = args.clients
        
        if args.wait_for_clients and num_clients > 0:
            input(f"Press Enter to start {num_clients} client(s)...")
        
        for i in range(num_clients):
            player_name = f"Player{i+1}" if num_clients > 1 else None
            if not stack.start_client(player_name):
                print(f"Failed to start client {i+1}")
        
        if num_clients > 0:
            print(f"Started {num_clients} client(s)")
        
        # Keep running until interrupted
        print("\nMultiplayer stack is running...")
        print("Press Ctrl+C to stop all components")
        
        try:
            # Wait for server process to end
            if stack.server_process:
                stack.server_process.wait()
        except KeyboardInterrupt:
            pass
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        stack.stop_all()


if __name__ == "__main__":
    main() 