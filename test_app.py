import sys
import os
import asyncio
import httpx

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.main import app
from app.core.database import init_db

async def run_tests():
    # Initialize DB directly
    init_db()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Test Dashboard (reviewer)
        resp = await client.get("/")
        assert resp.status_code == 200, f"Dashboard failed: {resp.status_code}"
        assert "BrandShield" in resp.text
        assert "Brand Governance Dashboard" in resp.text
        assert "Content Reviewed" in resp.text
        print("✓ Dashboard '/' OK (200)")

        # 2. Test Creator Role View
        resp = await client.get("/?role=creator")
        assert resp.status_code == 200
        assert "Alex Chen" in resp.text
        print("✓ Creator view '/?role=creator' OK (200)")

        # 3. Test Content Review
        resp = await client.get("/content")
        assert resp.status_code == 200
        assert "Content Review & Compliance Vault" in resp.text
        print("✓ Content Review '/content' OK (200)")

        # 4. Test Brand Memory
        resp = await client.get("/brand-memory")
        assert resp.status_code == 200
        assert "Brand Memory & Guideline Governance" in resp.text
        print("✓ Brand Memory '/brand-memory' OK (200)")

        # 5. Test Assets
        resp = await client.get("/assets")
        assert resp.status_code == 200
        assert "Approved Asset & Claim Library" in resp.text
        print("✓ Assets '/assets' OK (200)")

        # 6. Test Approvals
        resp = await client.get("/approvals")
        assert resp.status_code == 200
        assert "Pending Approvals Queue" in resp.text
        print("✓ Approvals '/approvals' OK (200)")

        # 7. Test Analytics
        resp = await client.get("/analytics")
        assert resp.status_code == 200
        assert "Brand Governance & Compliance Analytics" in resp.text
        print("✓ Analytics '/analytics' OK (200)")

        # 8. Test Settings
        resp = await client.get("/settings")
        assert resp.status_code == 200
        assert "System Settings & Governance Config" in resp.text
        print("✓ Settings '/settings' OK (200)")

        # 9. Test Submission Form POST
        post_resp = await client.post(
            "/content/submit",
            data={
                "title": "Live Test Announcement Q4",
                "campaign": "Cloud Launch 2026",
                "channel": "LinkedIn & Social",
                "content_text": "Our product delivers verified reliability and compliance across enterprise deployments.",
                "author_name": "Alex Chen"
            }
        )
        assert post_resp.status_code == 303, f"Submit failed: {post_resp.status_code}"
        print("✓ Submit Content POST '/content/submit' redirected properly (303 Redirect)")

        # Verify submission now appears on dashboard
        resp = await client.get("/")
        assert "Live Test Announcement Q4" in resp.text
        print("✓ Submitted content successfully rendered on Dashboard!")

    print("\n==========================================")
    print("ALL PHASE 1 REQUIREMENTS VERIFIED & PASSED!")
    print("==========================================")

if __name__ == "__main__":
    asyncio.run(run_tests())
