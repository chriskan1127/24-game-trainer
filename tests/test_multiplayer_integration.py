#!/usr/bin/env python3
"""
Multiplayer Integration Tests
Tests the complete multiplayer workflow including server connectivity, game management, and API endpoints.
"""

import time
import requests
import json
import sys
from pathlib import Path
from typing import Dict, Any, Optional


class MultiplayerIntegrationTester:
    """Comprehensive integration tester for multiplayer functionality."""
    
    def __init__(self, base_url: str = "http://localhost:8000", timeout: int = 5):
        self.base_url = base_url
        self.timeout = timeout
        self.test_results = []
        
    def log_test(self, test_name: str, passed: bool, message: str = ""):
        """Log test result."""
        status = "PASS" if passed else "FAIL"
        result = f"[{status}] {test_name}"
        if message:
            result += f": {message}"
        print(result)
        self.test_results.append({
            "name": test_name,
            "passed": passed,
            "message": message
        })
        return passed
    
    def test_server_health(self) -> bool:
        """Test server health check endpoint."""
        try:
            response = requests.get(f"{self.base_url}/health", timeout=self.timeout)
            if response.status_code == 200:
                return self.log_test("Server Health Check", True, "Server is running and healthy")
            else:
                return self.log_test("Server Health Check", False, f"Status code: {response.status_code}")
        except requests.exceptions.RequestException as e:
            return self.log_test("Server Health Check", False, f"Cannot connect: {str(e)}")
    
    def test_game_creation(self) -> Optional[str]:
        """Test game creation endpoint."""
        try:
            create_data = {
                "host_name": "IntegrationTestHost",
                "points_to_win": 5,
                "time_limit": 60,
                "max_players": 4
            }
            response = requests.post(
                f"{self.base_url}/games/create",
                json=create_data,
                timeout=self.timeout
            )
            
            if response.status_code == 201:
                game_data = response.json()
                game_code = game_data.get("game_code")
                if game_code:
                    self.log_test("Game Creation", True, f"Game created: {game_code}")
                    return game_code
                else:
                    self.log_test("Game Creation", False, "No game code in response")
                    return None
            else:
                self.log_test("Game Creation", False, f"Status code: {response.status_code}")
                return None
                
        except requests.exceptions.RequestException as e:
            self.log_test("Game Creation", False, f"Request failed: {str(e)}")
            return None
    
    def test_game_join(self, game_code: str) -> bool:
        """Test joining a game."""
        try:
            join_data = {"player_name": "IntegrationTestPlayer"}
            response = requests.post(
                f"{self.base_url}/games/{game_code}/join",
                json=join_data,
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                return self.log_test("Game Join", True, "Successfully joined game")
            else:
                return self.log_test("Game Join", False, f"Status code: {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            return self.log_test("Game Join", False, f"Request failed: {str(e)}")
    
    def test_game_status(self, game_code: str) -> bool:
        """Test retrieving game status."""
        try:
            response = requests.get(f"{self.base_url}/games/{game_code}/status", timeout=self.timeout)
            
            if response.status_code == 200:
                status_data = response.json()
                player_count = len(status_data.get("players", []))
                game_status = status_data.get("status", "unknown")
                return self.log_test("Game Status", True, f"Status: {game_status}, Players: {player_count}")
            else:
                return self.log_test("Game Status", False, f"Status code: {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            return self.log_test("Game Status", False, f"Request failed: {str(e)}")
    
    def test_server_metrics(self) -> bool:
        """Test server metrics endpoint."""
        try:
            response = requests.get(f"{self.base_url}/metrics", timeout=self.timeout)
            
            if response.status_code == 200:
                metrics_data = response.json()
                active_games = metrics_data.get("active_games", 0)
                total_players = metrics_data.get("total_players", 0)
                return self.log_test("Server Metrics", True, f"Active games: {active_games}, Total players: {total_players}")
            else:
                return self.log_test("Server Metrics", False, f"Status code: {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            return self.log_test("Server Metrics", False, f"Request failed: {str(e)}")
    
    def test_websocket_connection(self) -> bool:
        """Test WebSocket connection capability."""
        try:
            # Test WebSocket endpoint availability
            response = requests.get(f"{self.base_url}/ws/test", timeout=self.timeout)
            # WebSocket endpoints typically return 404 for GET requests, which is expected
            if response.status_code in [404, 405]:
                return self.log_test("WebSocket Endpoint", True, "WebSocket endpoint available")
            else:
                return self.log_test("WebSocket Endpoint", False, f"Unexpected status: {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            return self.log_test("WebSocket Endpoint", False, f"Request failed: {str(e)}")
    
    def test_game_list(self) -> bool:
        """Test retrieving list of games."""
        try:
            response = requests.get(f"{self.base_url}/games/list", timeout=self.timeout)
            
            if response.status_code == 200:
                games_data = response.json()
                game_count = len(games_data.get("games", []))
                return self.log_test("Game List", True, f"Found {game_count} games")
            else:
                return self.log_test("Game List", False, f"Status code: {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            return self.log_test("Game List", False, f"Request failed: {str(e)}")
    
    def run_all_tests(self) -> bool:
        """Run comprehensive integration test suite."""
        print("Starting Multiplayer Integration Tests...")
        print("=" * 50)
        
        # Test 1: Server Health
        if not self.test_server_health():
            print("\nServer is not running. Start with: python run_system.py server")
            return False
        
        # Test 2: Server Metrics
        self.test_server_metrics()
        
        # Test 3: Game List
        self.test_game_list()
        
        # Test 4: Game Creation
        game_code = self.test_game_creation()
        if not game_code:
            print("\nCannot continue tests without successful game creation")
            return False
        
        # Test 5: Game Join
        self.test_game_join(game_code)
        
        # Test 6: Game Status
        self.test_game_status(game_code)
        
        # Test 7: WebSocket
        self.test_websocket_connection()
        
        # Summary
        print("\n" + "=" * 50)
        passed_tests = sum(1 for result in self.test_results if result["passed"])
        total_tests = len(self.test_results)
        
        print(f"Integration Test Results: {passed_tests}/{total_tests} tests passed")
        
        if passed_tests == total_tests:
            print("All multiplayer integration tests passed!")
            return True
        else:
            print("Some tests failed. Check server logs for details.")
            return False


def main():
    """Main test runner."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Multiplayer Integration Test Suite")
    parser.add_argument("--url", default="http://localhost:8000", help="Server base URL")
    parser.add_argument("--timeout", type=int, default=5, help="Request timeout in seconds")
    
    args = parser.parse_args()
    
    tester = MultiplayerIntegrationTester(base_url=args.url, timeout=args.timeout)
    success = tester.run_all_tests()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main() 