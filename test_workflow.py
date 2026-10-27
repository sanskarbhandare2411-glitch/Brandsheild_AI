"""
test_workflow.py — Phase 4 approval workflow tests.

Tests:
1.  Creator submits → status becomes HUMAN_REVIEW or CHANGES_REQUESTED (never APPROVED)
2.  Creator submits → ContentRevision v1 persisted
3.  Reviewer approves → ReviewDecision created, status = APPROVED, approved_by set
4.  Creator (role=creator) cannot approve content → HTTP 303 redirect with forbidden flag
5.  Creator resubmits after changes_requested → prior approval invalidated, new version created
6.  Reviewer requests changes → status = CHANGES_REQUESTED, ReviewDecision with decision='changes_requested'
7.  Reviewer rejects → status = REJECTED, ReviewDecision with decision='rejected'
8.  Full revision history shows all versions after two submissions
9.  Resubmit from APPROVED state is refused (must go through reviewer first)
10. Recheck does not auto-approve content
"""

import sys
import os
import threading
import time
import urllib.request
import urllib.parse
import urllib.error

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Use an isolated test database so we don't corrupt the dev database
os.environ["DATABASE_URL"] = "sqlite:///./test_workflow.db"

from sqlmodel import Session, select
from app.core.database import engine, init_db
from app.core.models import (
    ContentSubmission, ContentStatus, ContentRevision,
    ReviewDecision, ActivityLog, Role
)
from app.main import app


# ---------------------------------------------------------------------------
# Test server helpers
# ---------------------------------------------------------------------------

PORT = 18523
BASE = f"http://127.0.0.1:{PORT}"
_server_thread = None


def start_test_server():
    global _server_thread
    import uvicorn
    config = uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="error")
    server = uvicorn.Server(config)

    def run():
        server.run()

    _server_thread = threading.Thread(target=run, daemon=True)
    _server_thread.start()
    # Wait for server to be ready
    for _ in range(30):
        try:
            urllib.request.urlopen(f"{BASE}/")
            return True
        except Exception:
            time.sleep(0.3)
    return False


def post(path, data: dict, follow_redirects=True) -> tuple[int, str]:
    """POST with form-encoded data. Returns (final_status_code, final_url)."""
    encoded = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(
        f"{BASE}{path}", data=encoded,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST"
    )
    try:
        resp = urllib.request.urlopen(req)
        return resp.status, resp.url
    except urllib.error.HTTPError as e:
        return e.code, str(e.url)


def get(path) -> tuple[int, str]:
    """GET and return (status_code, body)."""
    try:
        resp = urllib.request.urlopen(f"{BASE}{path}")
        return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, ""


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def get_latest_submission() -> ContentSubmission | None:
    with Session(engine) as s:
        return s.exec(
            select(ContentSubmission).order_by(ContentSubmission.id.desc())
        ).first()


def get_submission(sub_id: int) -> ContentSubmission | None:
    with Session(engine) as s:
        return s.get(ContentSubmission, sub_id)


def get_revisions(sub_id: int) -> list[ContentRevision]:
    with Session(engine) as s:
        return s.exec(
            select(ContentRevision)
            .where(ContentRevision.submission_id == sub_id)
            .order_by(ContentRevision.version_number)
        ).all()


def get_decisions(sub_id: int) -> list[ReviewDecision]:
    with Session(engine) as s:
        return s.exec(
            select(ReviewDecision)
            .where(ReviewDecision.submission_id == sub_id)
            .order_by(ReviewDecision.decided_at)
        ).all()


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

RESULTS: list[tuple[str, bool, str]] = []


def record(name: str, passed: bool, detail: str = ""):
    status = "PASS" if passed else "FAIL"
    RESULTS.append((name, passed, detail))
    print(f"  {status}  {name}" + (f"\n         {detail}" if detail and not passed else ""))


def submit_sample(title="Test Content", issues=True) -> int:
    """Submit a new content item and return its ID."""
    content = (
        "Our bulletproof magic AI cuts all costs in half guaranteed with 100% unbreakable security!"
        if issues
        else "BrandShield AI delivers verified 99.99% uptime across multi-region clusters with human-in-the-loop governance."
    )
    post("/content/submit", {
        "title": title,
        "campaign": "Test Campaign",
        "channel": "Web",
        "content_text": content,
        "author_name": "Alex Chen",
        "role": "creator",
    })
    sub = get_latest_submission()
    return sub.id if sub else -1


# ---------------------------------------------------------------------------

def test_1_submit_never_approved():
    """Creator submits → status is HUMAN_REVIEW or CHANGES_REQUESTED, never APPROVED."""
    sub_id = submit_sample("T1 Never Auto-Approved", issues=False)
    sub = get_submission(sub_id)
    if not sub:
        record("1. Submit never auto-approved", False, "Submission not found in DB")
        return
    passed = sub.status != ContentStatus.APPROVED
    record("1. Submit never auto-approved",
           passed, f"status={sub.status.value}")


def test_2_revision_created_on_submit():
    """ContentRevision v1 is persisted when a new submission is created."""
    sub_id = submit_sample("T2 Revision Persisted")
    revs = get_revisions(sub_id)
    passed = len(revs) >= 1 and revs[0].version_number == 1
    record("2. ContentRevision v1 persisted on submit",
           passed, f"revisions={[r.version_number for r in revs]}")


def test_3_reviewer_approves():
    """Reviewer approves → ReviewDecision created, status=APPROVED, approved_by set."""
    sub_id = submit_sample("T3 Reviewer Approve")
    code, url = post(f"/approvals/{sub_id}/approve", {
        "role": "reviewer",
        "reviewer_name": "Morgan Vance",
        "comments": "Approved — compliant copy.",
    })
    sub = get_submission(sub_id)
    decs = get_decisions(sub_id)
    passed = (
        sub is not None
        and sub.status == ContentStatus.APPROVED
        and sub.approved_by == "Morgan Vance"
        and sub.approved_at is not None
        and len(decs) >= 1
        and decs[-1].decision == "approved"
    )
    record("3. Reviewer approves → APPROVED + ReviewDecision",
           passed,
           f"status={sub.status.value if sub else 'N/A'} "
           f"approved_by={sub.approved_by if sub else 'N/A'} "
           f"decisions={len(decs)}")


def test_4_creator_cannot_approve():
    """Creator role is forbidden from approving → redirected with forbidden flag."""
    sub_id = submit_sample("T4 Creator Cannot Approve")
    code, url = post(f"/approvals/{sub_id}/approve", {
        "role": "creator",
        "reviewer_name": "Alex Chen",
        "comments": "I approve my own content.",
    })
    sub = get_submission(sub_id)
    # Should NOT be approved; redirect URL should contain 'forbidden'
    not_approved = sub is not None and sub.status != ContentStatus.APPROVED
    redirected_correctly = "forbidden" in url
    passed = not_approved and redirected_correctly
    record("4. Creator cannot approve content",
           passed,
           f"status={sub.status.value if sub else 'N/A'} url={url}")


def test_5_resubmit_invalidates_prior_approval():
    """Creator resubmits after approval → prior approval cleared, new version saved."""
    sub_id = submit_sample("T5 Resubmit Invalidates Approval")

    # First: reviewer approves
    post(f"/approvals/{sub_id}/approve", {
        "role": "reviewer",
        "reviewer_name": "Morgan Vance",
        "comments": "Initially approved.",
    })
    sub_before = get_submission(sub_id)
    assert sub_before and sub_before.status == ContentStatus.APPROVED, "Pre-condition: must be APPROVED"

    # Reviewer requests changes (to allow resubmit)
    post(f"/approvals/{sub_id}/request_changes", {
        "role": "reviewer",
        "reviewer_name": "Morgan Vance",
        "comments": "Actually, needs revision.",
    })

    # Creator resubmits
    code, url = post(f"/content/{sub_id}/resubmit", {
        "role": "creator",
        "content_text": "BrandShield AI delivers verified 99.99% uptime with human-in-the-loop governance.",
        "change_summary": "Removed prohibited terminology per reviewer feedback.",
    })
    sub_after = get_submission(sub_id)
    revs = get_revisions(sub_id)

    prior_approval_cleared = (
        sub_after is not None
        and sub_after.approved_by is None
        and sub_after.approved_at is None
    )
    new_version = sub_after is not None and (sub_after.current_version or 1) >= 2
    history_saved = len(revs) >= 2

    passed = prior_approval_cleared and new_version and history_saved
    record("5. Resubmit invalidates prior approval",
           passed,
           f"approved_by={sub_after.approved_by if sub_after else 'N/A'} "
           f"version={sub_after.current_version if sub_after else 'N/A'} "
           f"revisions={len(revs)}")


def test_6_reviewer_requests_changes():
    """Reviewer requests changes → CHANGES_REQUESTED, ReviewDecision recorded."""
    sub_id = submit_sample("T6 Request Changes")
    post(f"/approvals/{sub_id}/request_changes", {
        "role": "reviewer",
        "reviewer_name": "Morgan Vance",
        "comments": "Please remove the superlative claims.",
    })
    sub = get_submission(sub_id)
    decs = get_decisions(sub_id)
    passed = (
        sub is not None
        and sub.status == ContentStatus.CHANGES_REQUESTED
        and len(decs) >= 1
        and decs[-1].decision == "changes_requested"
    )
    record("6. Reviewer requests changes → CHANGES_REQUESTED + ReviewDecision",
           passed,
           f"status={sub.status.value if sub else 'N/A'} decisions={len(decs)}")


def test_7_reviewer_rejects():
    """Reviewer rejects → REJECTED, ReviewDecision with decision='rejected'."""
    sub_id = submit_sample("T7 Reject")
    post(f"/approvals/{sub_id}/reject", {
        "role": "reviewer",
        "reviewer_name": "Morgan Vance",
        "comments": "Content violates multiple brand policies and cannot be revised.",
    })
    sub = get_submission(sub_id)
    decs = get_decisions(sub_id)
    passed = (
        sub is not None
        and sub.status == ContentStatus.REJECTED
        and len(decs) >= 1
        and decs[-1].decision == "rejected"
        and sub.approved_by is None
    )
    record("7. Reviewer rejects → REJECTED + ReviewDecision",
           passed,
           f"status={sub.status.value if sub else 'N/A'} decisions={len(decs)}")


def test_8_full_revision_history():
    """Full revision history shows all versions after two round-trips."""
    sub_id = submit_sample("T8 Revision History")

    # Reviewer requests changes
    post(f"/approvals/{sub_id}/request_changes", {
        "role": "reviewer",
        "reviewer_name": "Morgan Vance",
        "comments": "Needs cleanup.",
    })

    # Creator resubmits
    post(f"/content/{sub_id}/resubmit", {
        "role": "creator",
        "content_text": "BrandShield AI provides verified 99.99% uptime with enterprise-grade governance.",
        "change_summary": "Cleaned up prohibited terms.",
    })

    revs = get_revisions(sub_id)
    passed = len(revs) >= 2 and revs[0].version_number == 1 and revs[1].version_number == 2
    record("8. Full revision history shows all versions",
           passed,
           f"versions={[r.version_number for r in revs]}")


def test_9_cannot_resubmit_from_approved():
    """Resubmit from APPROVED state is not allowed without reviewer action."""
    sub_id = submit_sample("T9 No Resubmit from Approved")
    # Approve it
    post(f"/approvals/{sub_id}/approve", {
        "role": "reviewer",
        "reviewer_name": "Morgan Vance",
        "comments": "Approved.",
    })
    sub = get_submission(sub_id)
    assert sub and sub.status == ContentStatus.APPROVED

    # Try to resubmit — expect 400 or redirect
    try:
        code, url = post(f"/content/{sub_id}/resubmit", {
            "role": "creator",
            "content_text": "New content attempting to bypass approval.",
            "change_summary": "Trying to bypass.",
        })
        sub_after = get_submission(sub_id)
        # Should still be APPROVED or the resubmit should have been refused (400)
        still_approved = sub_after is not None and sub_after.status == ContentStatus.APPROVED
        record("9. Cannot resubmit from APPROVED state",
               code in (400, 303) or still_approved,
               f"code={code} status={sub_after.status.value if sub_after else 'N/A'}")
    except urllib.error.HTTPError as e:
        record("9. Cannot resubmit from APPROVED state", e.code == 400, f"HTTP {e.code}")


def test_10_recheck_never_approves():
    """Recheck endpoint does not auto-approve content."""
    sub_id = submit_sample("T10 Recheck No Auto-Approve", issues=False)
    post(f"/content/{sub_id}/recheck", {"role": "reviewer"})
    sub = get_submission(sub_id)
    passed = sub is not None and sub.status != ContentStatus.APPROVED
    record("10. Recheck never auto-approves",
           passed,
           f"status={sub.status.value if sub else 'N/A'}")


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("\n==============================================")
    print("  BrandShield AI -- Phase 4 Workflow Tests")
    print("==============================================\n")

    print("▶ Initialising isolated test database…")
    init_db()
    print("  DB ready.\n")

    print("▶ Starting test server on port", PORT, "…")
    ok = start_test_server()
    if not ok:
        print("  ❌ Could not start test server. Aborting.")
        sys.exit(1)
    print("  Server ready.\n")

    print("Running tests:\n")
    test_1_submit_never_approved()
    test_2_revision_created_on_submit()
    test_3_reviewer_approves()
    test_4_creator_cannot_approve()
    test_5_resubmit_invalidates_prior_approval()
    test_6_reviewer_requests_changes()
    test_7_reviewer_rejects()
    test_8_full_revision_history()
    test_9_cannot_resubmit_from_approved()
    test_10_recheck_never_approves()

    print("\n==============================================")
    passed = sum(1 for _, p, _ in RESULTS if p)
    total = len(RESULTS)
    print(f"  Result: {passed}/{total} tests passed")
    print("==============================================\n")

    # Cleanup test DB
    try:
        if os.path.exists("test_workflow.db"):
            os.remove("test_workflow.db")
    except Exception:
        pass

    sys.exit(0 if passed == total else 1)
