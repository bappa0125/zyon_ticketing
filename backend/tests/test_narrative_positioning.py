"""Tests for narrative positioning API."""
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_narrative_positioning_empty_client():
    """GET without client returns 200 with empty reports."""
    resp = client.get("/api/social/narrative-positioning?client=&days=7")
    assert resp.status_code == 200
    data = resp.json()
    assert "reports" in data
    assert data["reports"] == []


@patch("app.services.narrative_positioning_service.load_positioning", new_callable=AsyncMock)
def test_narrative_positioning_returns_reports(mock_load):
    """GET with client returns reports from DB."""
    mock_load.return_value = [
        {
            "client": "Sahi",
            "date": "2025-03-08",
            "computed_at": "2025-03-08T10:00:00",
            "narratives": [{"theme": "Retail trading", "sentiment": "mixed"}],
            "positioning": {"headline": "Headline", "pitch_angle": "Pitch", "suggested_outlets": []},
            "threats": [],
            "opportunities": [],
            "evidence_refs": [],
        }
    ]
    resp = client.get("/api/social/narrative-positioning?client=Sahi&days=7")
    assert resp.status_code == 200
    data = resp.json()
    assert "reports" in data
    assert len(data["reports"]) == 1
    assert data["reports"][0]["client"] == "Sahi"
    assert data["reports"][0]["date"] == "2025-03-08"
    assert "narratives" in data["reports"][0]
    assert "positioning" in data["reports"][0]
    assert "threats" in data["reports"][0]
    assert "opportunities" in data["reports"][0]
