import requests
import json

BASE_URL = "http://127.0.0.1:8000"

def test_flow():
    # 1. Login
    login_data = {"username": "admin", "password": "Admin@PrintHub2026"}
    print(f"Logging in with {login_data['username']}...")
    resp = requests.post(f"{BASE_URL}/auth/login", json=login_data)
    print(f"Login Status: {resp.status_code}")
    if resp.status_code != 200:
        print(f"Login Failed: {resp.text}")
        return
    
    data = resp.json()
    token = data["access_token"]
    print(f"Token obtained: {token[:20]}...")

    # 2. Change Password
    change_data = {
        "current_password": "Admin@PrintHub2026",
        "new_password": "Admin@123456"
    }
    print(f"Changing password...")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    resp = requests.post(f"{BASE_URL}/auth/change-password", json=change_data, headers=headers)
    print(f"Change Password Status: {resp.status_code}")
    print(f"Response Body: {resp.text}")

if __name__ == "__main__":
    test_flow()
