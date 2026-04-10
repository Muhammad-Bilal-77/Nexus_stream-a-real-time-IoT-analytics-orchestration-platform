import requests
import jwt
import sys

JWT_SECRET = "nexusstream-dev-jwt-secret-change-in-prod"
JWT_ALG = "HS256"

def get_token(role):
    return jwt.encode({"sub": f"test_{role}", "username": "Test", "roles": [role]}, JWT_SECRET, algorithm=JWT_ALG)

def run():
    base_url = "http://localhost:8002/api/v1"
    
    # 1. Health
    print(f"GET /health: {requests.get('http://localhost:8002/health').status_code}")
    
    # 2. Viewer
    headers = {"Authorization": f"Bearer {get_token('viewer')}"}
    r = requests.get(f"{base_url}/stats/overview", headers=headers)
    print(f"Viewer GET /stats/overview: {r.status_code}")
    
    r = requests.get(f"{base_url}/anomalies", headers=headers)
    print(f"Viewer GET /anomalies: {r.status_code} (Expect 403)")
    
    # 3. Analyst
    headers = {"Authorization": f"Bearer {get_token('analyst')}"}
    r = requests.get(f"{base_url}/anomalies", headers=headers)
    print(f"Analyst GET /anomalies: {r.status_code}")
    
    # 4. Admin
    headers = {"Authorization": f"Bearer {get_token('admin')}"}
    r = requests.get(f"{base_url}/admin/stats", headers=headers)
    print(f"Admin GET /admin/stats: {r.status_code}")

if __name__ == "__main__":
    run()
