#!/usr/bin/env python3
"""
Full System Test Suite
Comprehensive testing of both single-player and multiplayer components of the 24-Game system.
"""

import sys
import subprocess
import time
import threading
import signal
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Import the multiplayer integration tester
from test_multiplayer_integration import MultiplayerIntegrationTester


class SystemTester:
    """Comprehensive system tester for the entire 24-Game application."""
    
    def __init__(self):
        self.test_results = {}
        self.server_process = None
        self.original_dir = os.getcwd()
        
    def log_result(self, test_name: str, success: bool, message: str = ""):
        """Log test result."""
        self.test_results[test_name] = {
            "success": success,
            "message": message
        }
        status = "PASS" if success else "FAIL"
        result = f"[{status}] {test_name}"
        if message:
            result += f": {message}"
        print(result)
        
    def check_dependencies(self) -> bool:
        """Check if all required dependencies and files exist."""
        print("Checking system dependencies...")
        
        required_files = [
            "src/main.py",
            "src/multiplayer_main.py", 
            "server/start_server.py",
            "server/main.py",
            "environment.yml"
        ]
        
        missing_files = []
        for file_path in required_files:
            if not Path(file_path).exists():
                missing_files.append(file_path)
        
        if missing_files:
            self.log_result("Dependency Check", False, f"Missing files: {', '.join(missing_files)}")
            return False
        
        self.log_result("Dependency Check", True, "All required files found")
        return True
        
    def test_single_player_import(self) -> bool:
        """Test that single-player application can be imported without errors."""
        print("Testing single-player application import...")
        
        try:
            # Test if we can import the main modules
            result = subprocess.run([
                sys.executable, "-c", 
                "import sys; sys.path.insert(0, 'src'); import main; print('Import successful')"
            ], capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                self.log_result("Single-Player Import", True, "Main application imports successfully")
                return True
            else:
                self.log_result("Single-Player Import", False, f"Import error: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            self.log_result("Single-Player Import", False, "Import test timed out")
            return False
        except Exception as e:
            self.log_result("Single-Player Import", False, f"Exception: {str(e)}")
            return False
    
    def test_server_unit_tests(self) -> bool:
        """Run the server unit tests."""
        print("Running server unit tests...")
        
        try:
            # Change to server directory
            os.chdir("server")
            
            # Run pytest
            result = subprocess.run([
                sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short"
            ], capture_output=True, text=True, timeout=120)
            
            if result.returncode == 0:
                # Count test results
                output_lines = result.stdout.split('\n')
                test_summary = [line for line in output_lines if 'passed' in line and ('failed' in line or 'error' in line or 'passed' in line)]
                
                if test_summary:
                    self.log_result("Server Unit Tests", True, f"Unit tests passed: {test_summary[-1]}")
                else:
                    self.log_result("Server Unit Tests", True, "All unit tests passed")
                return True
            else:
                self.log_result("Server Unit Tests", False, f"Tests failed: {result.stdout[-500:]}")
                return False
                
        except subprocess.TimeoutExpired:
            self.log_result("Server Unit Tests", False, "Unit tests timed out")
            return False
        except Exception as e:
            self.log_result("Server Unit Tests", False, f"Exception: {str(e)}")
            return False
        finally:
            os.chdir(self.original_dir)
    
    def start_test_server(self) -> bool:
        """Start the server for integration testing."""
        print("Starting test server...")
        
        try:
            # Change to server directory
            os.chdir("server")
            
            # Start server in background
            self.server_process = subprocess.Popen([
                sys.executable, "start_server.py"
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            # Wait for server to start
            time.sleep(5)
            
            # Check if server is still running
            if self.server_process.poll() is None:
                self.log_result("Server Startup", True, "Test server started successfully")
                return True
            else:
                stdout, stderr = self.server_process.communicate()
                self.log_result("Server Startup", False, f"Server failed to start: {stderr.decode()}")
                return False
                
        except Exception as e:
            self.log_result("Server Startup", False, f"Exception starting server: {str(e)}")
            return False
        finally:
            os.chdir(self.original_dir)
    
    def stop_test_server(self):
        """Stop the test server."""
        if self.server_process:
            try:
                self.server_process.terminate()
                self.server_process.wait(timeout=10)
                print("Test server stopped")
            except subprocess.TimeoutExpired:
                self.server_process.kill()
                print("Test server forcefully stopped")
            except Exception as e:
                print(f"Error stopping server: {e}")
    
    def test_multiplayer_integration(self) -> bool:
        """Run multiplayer integration tests."""
        print("Running multiplayer integration tests...")
        
        try:
            # Create integration tester
            tester = MultiplayerIntegrationTester(timeout=10)
            
            # Run tests
            success = tester.run_all_tests()
            
            if success:
                self.log_result("Multiplayer Integration", True, "All integration tests passed")
            else:
                failed_tests = [result for result in tester.test_results if not result["passed"]]
                self.log_result("Multiplayer Integration", False, f"{len(failed_tests)} tests failed")
            
            return success
            
        except Exception as e:
            self.log_result("Multiplayer Integration", False, f"Exception: {str(e)}")
            return False
    
    def test_database_operations(self) -> bool:
        """Test database initialization and basic operations."""
        print("Testing database operations...")
        
        try:
            os.chdir("server")
            
            # Test database initialization
            result = subprocess.run([
                sys.executable, "-c", 
                "from database.database import init_db; init_db(); print('Database initialized')"
            ], capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                self.log_result("Database Operations", True, "Database initialization successful")
                return True
            else:
                self.log_result("Database Operations", False, f"Database error: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            self.log_result("Database Operations", False, "Database test timed out")
            return False
        except Exception as e:
            self.log_result("Database Operations", False, f"Exception: {str(e)}")
            return False
        finally:
            os.chdir(self.original_dir)
    
    def run_comprehensive_tests(self) -> bool:
        """Run the complete test suite."""
        print("Starting Comprehensive System Tests")
        print("=" * 60)
        
        all_passed = True
        
        try:
            # 1. Check dependencies
            if not self.check_dependencies():
                all_passed = False
                print("Cannot continue - missing dependencies")
                return False
            
            # 2. Test single-player imports
            if not self.test_single_player_import():
                all_passed = False
            
            # 3. Test database operations
            if not self.test_database_operations():
                all_passed = False
            
            # 4. Run server unit tests
            if not self.test_server_unit_tests():
                all_passed = False
            
            # 5. Start server for integration tests
            if self.start_test_server():
                # 6. Run integration tests
                if not self.test_multiplayer_integration():
                    all_passed = False
            else:
                all_passed = False
                
        finally:
            # Always stop the server
            self.stop_test_server()
        
        # Print summary
        print("\n" + "=" * 60)
        print("SYSTEM TEST SUMMARY")
        print("=" * 60)
        
        passed_count = sum(1 for result in self.test_results.values() if result["success"])
        total_count = len(self.test_results)
        
        for test_name, result in self.test_results.items():
            status = "PASS" if result["success"] else "FAIL"
            print(f"[{status}] {test_name}")
            if result["message"]:
                print(f"    {result['message']}")
        
        print(f"\nResults: {passed_count}/{total_count} test categories passed")
        
        if all_passed:
            print("ALL SYSTEM TESTS PASSED!")
        else:
            print("SOME TESTS FAILED - Check individual results above")
            
        return all_passed


def main():
    """Main test runner."""
    import argparse
    
    parser = argparse.ArgumentParser(description="24-Game Full System Test Suite")
    parser.add_argument("--quick", action="store_true", help="Run quick tests only (skip integration)")
    
    args = parser.parse_args()
    
    tester = SystemTester()
    
    if args.quick:
        print("Running quick system tests...")
        success = (tester.check_dependencies() and 
                  tester.test_single_player_import() and
                  tester.test_database_operations() and
                  tester.test_server_unit_tests())
    else:
        success = tester.run_comprehensive_tests()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main() 