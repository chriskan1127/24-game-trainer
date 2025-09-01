#!/usr/bin/env python3
"""
24-Game System Management
Unified script to manage environment, testing, and running both single-player and multiplayer versions
"""

import subprocess
import sys
import os
import argparse
import time
from pathlib import Path
from typing import List, Optional

def run_command(command: str, cwd: Optional[str] = None) -> bool:
    """Run a command and return success status"""
    try:
        print(f"Running: {command}")
        if cwd:
            print(f"Working directory: {cwd}")
        result = subprocess.run(
            command, 
            shell=True, 
            check=True, 
            cwd=cwd,
            capture_output=False
        )
        return result.returncode == 0
    except subprocess.CalledProcessError as e:
        print(f"Command failed with return code {e.returncode}")
        return False
    except Exception as e:
        print(f"Unexpected error running command: {e}")
        return False

def check_file_exists(file_path: Path, description: str) -> bool:
    """Check if a file exists and provide helpful error message if not"""
    if not file_path.exists():
        print(f"Error: {description} not found at {file_path}")
        return False
    return True

def setup_environment():
    """Set up the conda environment with all dependencies."""
    print("Setting up 24-Game environment...")
    
    # Check if conda is available
    if not run_command("conda --version"):
        print("Error: Conda is not available. Please install Miniconda or Anaconda.")
        print("Visit: https://docs.conda.io/en/latest/miniconda.html")
        return False
    
    # Check if environment file exists
    env_file = Path("environment.yml")
    if not check_file_exists(env_file, "Environment file (environment.yml)"):
        return False
    
    # Try to create environment first, if it fails try to update
    print("Attempting to create environment...")
    if run_command("conda env create -f environment.yml"):
        return True
    
    print("Environment may already exist, attempting to update...")
    return run_command("conda env update -f environment.yml")

def update_environment():
    """Update the existing conda environment."""
    print("Updating 24-Game environment...")
    
    env_file = Path("environment.yml")
    if not check_file_exists(env_file, "Environment file (environment.yml)"):
        return False
    
    return run_command("conda env update -f environment.yml")

def run_frontend():
    """Run the single-player Kivy frontend application."""
    print("Starting single-player frontend application...")
    
    frontend_script = Path("src/main.py")
    if not check_file_exists(frontend_script, "Single-player frontend main.py"):
        return False
    
    return run_command(f'"{sys.executable}" "{frontend_script}"')

def run_multiplayer_client():
    """Run the multiplayer Kivy client application."""
    print("Starting multiplayer client application...")
    
    multiplayer_script = Path("src/multiplayer_main.py")
    if not check_file_exists(multiplayer_script, "Multiplayer client main.py"):
        return False
    
    return run_command(f'"{sys.executable}" "{multiplayer_script}"')

def run_server():
    """Run the multiplayer server."""
    print("Starting multiplayer server...")
    
    server_script = Path("server/start_server.py")
    if not check_file_exists(server_script, "Server start script"):
        return False
    
    return run_command(f'"{sys.executable}" "{server_script}"')

def run_multiplayer_stack():
    """Run the complete multiplayer stack (server + clients)."""
    print("Starting complete multiplayer stack...")
    
    stack_script = Path("scripts/start_multiplayer_stack.py")
    if not check_file_exists(stack_script, "Multiplayer stack script"):
        return False
    
    return run_command(f'"{sys.executable}" "{stack_script}" --client')

def init_database():
    """Initialize the database for the multiplayer server."""
    print("Initializing database...")
    
    server_dir = Path("server")
    if not server_dir.exists():
        print("Error: Server directory not found")
        return False
    
    # Change to server directory
    original_dir = os.getcwd()
    try:
        os.chdir(server_dir)
        
        # Run database initialization
        result = run_command(f'"{sys.executable}" -c "from database.database import init_db; init_db()"')
        
        return result
    except Exception as e:
        print(f"Database initialization failed: {e}")
        return False
    finally:
        os.chdir(original_dir)

def run_unit_tests():
    """Run unit tests for the server."""
    print("Running unit tests...")
    
    server_dir = Path("server")
    if not server_dir.exists():
        print("Error: Server directory not found")
        return False
    
    tests_dir = server_dir / "tests"
    if not tests_dir.exists():
        print("Error: Tests directory not found in server/")
        return False
    
    # Change to server directory  
    original_dir = os.getcwd()
    try:
        os.chdir(server_dir)
        return run_command(f'"{sys.executable}" -m pytest tests/ -v')
    finally:
        os.chdir(original_dir)

def test_system():
    """Run comprehensive system tests."""
    print("Running comprehensive system tests...")
    
    test_script = Path("tests/test_full_system.py")
    if not check_file_exists(test_script, "System test script"):
        return False
    
    return run_command(f'"{sys.executable}" "{test_script}"')

def test_multiplayer_integration():
    """Test the multiplayer system integration."""
    print("Running multiplayer integration tests...")
    
    test_script = Path("tests/test_multiplayer_integration.py")
    if not check_file_exists(test_script, "Multiplayer integration test script"):
        return False
    
    return run_command(f'"{sys.executable}" "{test_script}"')

def test_quick():
    """Run quick tests (no integration testing)."""
    print("Running quick system tests...")
    
    test_script = Path("tests/test_full_system.py")
    if not check_file_exists(test_script, "System test script"):
        return False
    
    return run_command(f'"{sys.executable}" "{test_script}" --quick')

def main():
    """Main entry point for the system management script."""
    parser = argparse.ArgumentParser(
        description="24-Game System Management",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_system.py setup                  # Set up environment
  python run_system.py update                 # Update environment
  python run_system.py test                   # Run comprehensive system tests
  python run_system.py test-quick             # Run quick tests (no integration)
  python run_system.py frontend               # Start single-player Kivy frontend
  python run_system.py multiplayer            # Start multiplayer Kivy client
  python run_system.py server                 # Start multiplayer server only
  python run_system.py multiplayer-stack      # Start complete multiplayer stack
  python run_system.py init-db                # Initialize database
  python run_system.py unit-tests             # Run server unit tests
  python run_system.py test-multiplayer       # Test multiplayer integration
        """
    )
    
    parser.add_argument(
        "command",
        choices=[
            "setup", "update", "test", "test-quick", "frontend", "multiplayer", 
            "server", "multiplayer-stack", "init-db", "unit-tests", "test-multiplayer"
        ],
        help="Command to run"
    )
    
    args = parser.parse_args()
    
    commands = {
        "setup": setup_environment,
        "update": update_environment,
        "test": test_system,
        "test-quick": test_quick,
        "frontend": run_frontend,
        "multiplayer": run_multiplayer_client,
        "server": run_server,
        "multiplayer-stack": run_multiplayer_stack,
        "init-db": init_database,
        "unit-tests": run_unit_tests,
        "test-multiplayer": test_multiplayer_integration,
    }
    
    print(f"Executing command: {args.command}")
    success = commands[args.command]()
    
    if success:
        print(f"\nCommand '{args.command}' completed successfully!")
    else:
        print(f"\nCommand '{args.command}' failed!")
        sys.exit(1)

if __name__ == "__main__":
    main() 