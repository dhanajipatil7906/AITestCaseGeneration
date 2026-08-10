import os
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app

print('cwd', os.getcwd())
print('python', os.sys.executable)
client = TestClient(app)
print('health', client.get('/health').status_code, client.get('/health').json())
print('analysis routes', [route.path for route in app.router.routes if '/api/analysis' in route.path])
