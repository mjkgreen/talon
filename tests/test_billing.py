import pytest
from fastapi.testclient import TestClient
from talon.server import app

client = TestClient(app)

def test_billing_bypass():
    response = client.get("/health")
    assert response.status_code == 200

def test_premium_endpoints():
    response = client.get("/projects")
    assert response.status_code == 200
