import threading
import time
import urllib.request
import urllib.parse
import sys
import uvicorn
from app.main import app

def run_server():
    config = uvicorn.Config(app, host="127.0.0.1", port=8888, log_level="warning")
    server = uvicorn.Server(config)
    server.run()

def test_endpoints():
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    
    print("Waiting for server to start on port 8888...", flush=True)
    base_url = "http://127.0.0.1:8888"
    
    for _ in range(30):
        try:
            with urllib.request.urlopen(f"{base_url}/", timeout=2) as resp:
                if resp.status == 200:
                    print("Server is UP and responsive!", flush=True)
                    break
        except Exception:
            time.sleep(0.5)
    else:
        print("Error: Server failed to start in 15s", file=sys.stderr)
        sys.exit(1)

    # Test all views
    endpoints = [
        ("/", "Brand Governance Dashboard"),
        ("/?role=creator", "Alex Chen"),
        ("/content", "Content Review & Compliance Vault"),
        ("/brand-memory", "Brand Memory & Guideline Governance"),
        ("/assets", "Approved Asset & Claim Library"),
        ("/approvals", "Pending Approvals Queue"),
        ("/analytics", "Brand Governance & Compliance Analytics"),
        ("/settings", "System Settings & Governance Config"),
    ]

    for path, expected_text in endpoints:
        url = f"{base_url}{path}"
        with urllib.request.urlopen(url, timeout=5) as resp:
            content = resp.read().decode("utf-8")
            assert resp.status == 200, f"Expected 200 on {path}, got {resp.status}"
            assert expected_text in content, f"Expected '{expected_text}' in response from {path}"
            print(f"[OK] GET {path} returned 200 OK (verified content)", flush=True)

    # Test Content Submission POST
    submit_url = f"{base_url}/content/submit"
    post_data = urllib.parse.urlencode({
        "title": "Codex 48 Automated Verification Post",
        "campaign": "Sprint Validation",
        "channel": "LinkedIn & Social",
        "content_text": "Phase 1 dashboard navigation and content submission pipeline verified.",
        "author_name": "Alex Chen"
    }).encode("utf-8")

    req = urllib.request.Request(submit_url, data=post_data, method="POST")
    with urllib.request.urlopen(req, timeout=5) as resp:
        content = resp.read().decode("utf-8")
        assert resp.status == 200, f"Expected 200 after redirect, got {resp.status}"
        assert "Codex 48 Automated Verification Post" in content, "Submitted post not found in dashboard!"
        print("[OK] POST /content/submit succeeded and redirected to dashboard displaying new item!", flush=True)

    # Test Approvals view
    with urllib.request.urlopen(f"{base_url}/approvals", timeout=5) as resp:
        approvals_html = resp.read().decode("utf-8")
        assert "Pending Approvals Queue" in approvals_html
        print("[OK] Verified Approvals Queue functionality", flush=True)

    # Test Content Detail Inspection view
    with urllib.request.urlopen(f"{base_url}/content/1", timeout=5) as resp:
        detail_html = resp.read().decode("utf-8")
        assert "Compliance Findings" in detail_html or "Compliance Score" in detail_html
        assert "Flagged Text Snippet" in detail_html or "Suggested Correction" in detail_html
        print("[OK] Verified Content Detail inspection view with findings & citations", flush=True)

    print("\n=======================================================", flush=True)
    print("ALL 8 ENDPOINTS, STATIC PAGES, AND FORM POSTS VERIFIED!", flush=True)
    print("=======================================================", flush=True)

if __name__ == "__main__":
    test_endpoints()
