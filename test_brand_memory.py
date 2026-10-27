import sys
import os
import threading
import time
import urllib.request
import urllib.parse
from datetime import date
from sqlmodel import select

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uvicorn
from app.main import app
from app.core.database import Session, engine
from app.core.models import (
    VoiceToneGuideline, TerminologyRule, ProductFact, 
    ApprovedClaim, BrandAssetRef, VerificationStatus, TerminologyType
)

def run_server():
    config = uvicorn.Config(app, host="127.0.0.1", port=8989, log_level="warning")
    server = uvicorn.Server(config)
    server.run()

def run_brand_memory_tests():
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    
    print("Waiting for BrandShield test server on port 8989...", flush=True)
    base_url = "http://127.0.0.1:8989"
    
    for _ in range(30):
        try:
            with urllib.request.urlopen(f"{base_url}/brand-memory", timeout=2) as resp:
                if resp.status == 200:
                    print("Test Server is UP!", flush=True)
                    break
        except Exception:
            time.sleep(0.5)
    else:
        print("Error: Server failed to start", file=sys.stderr)
        sys.exit(1)

    # 1. TEST RETRIEVAL OF ALL 5 TABS
    tabs = ["voice", "terms", "facts", "claims", "assets"]
    for tab in tabs:
        url = f"{base_url}/brand-memory?tab={tab}&role=reviewer"
        with urllib.request.urlopen(url, timeout=5) as resp:
            content = resp.read().decode("utf-8")
            assert resp.status == 200
            print(f"[OK] Tab '{tab}' rendered successfully (200 OK)", flush=True)

    # 2. TEST ADDING A VOICE GUIDELINE (Reviewer role)
    post_voice = urllib.parse.urlencode({
        "title": "Partner Ecosystem Voice & Tone",
        "audience": "Global Technology Alliances",
        "tone_attributes": "Collaborative, Strategic, Growth-oriented",
        "dos_principles": "Highlight co-innovation and mutual security verification.",
        "donts_principles": "Do not imply endorsement without signed partnership tier.",
        "example_positive": "Co-engineered with certified cloud partners.",
        "example_negative": "Our partners guarantee 100% bug free deployment.",
        "role": "reviewer"
    }).encode("utf-8")
    req = urllib.request.Request(f"{base_url}/brand-memory/voice/add", data=post_voice, method="POST")
    with urllib.request.urlopen(req, timeout=5) as resp:
        assert resp.status == 200
        content = resp.read().decode("utf-8")
        assert "Partner Ecosystem Voice" in content
        print("[OK] Created new Voice Guideline and verified in list", flush=True)

    # 3. TEST PERMISSION ENFORCEMENT: Creator CANNOT add voice guideline directly
    post_voice_creator = urllib.parse.urlencode({
        "title": "Unauthorized Guideline",
        "audience": "Anyone",
        "tone_attributes": "Casual",
        "dos_principles": "Whatever",
        "donts_principles": "None",
        "role": "creator"
    }).encode("utf-8")
    req = urllib.request.Request(f"{base_url}/brand-memory/voice/add", data=post_voice_creator, method="POST")
    with urllib.request.urlopen(req, timeout=5) as resp:
        content = resp.read().decode("utf-8")
        assert "Permission Denied" in content or "Unauthorized Guideline" not in content
        print("[OK] Verified permission enforcement: Creator cannot add voice guidelines", flush=True)

    # 4. TEST ADDING A TERMINOLOGY RULE
    post_term = urllib.parse.urlencode({
        "term": "miracle cure for brand risk",
        "term_type": "prohibited",
        "replacement_term": "systematic compliance automation",
        "category": "Marketing Superlative",
        "reason": "Exaggerated medicinal metaphor undermines enterprise reliability.",
        "severity": "critical",
        "role": "reviewer"
    }).encode("utf-8")
    req = urllib.request.Request(f"{base_url}/brand-memory/terms/add", data=post_term, method="POST")
    with urllib.request.urlopen(req, timeout=5) as resp:
        content = resp.read().decode("utf-8")
        assert "miracle cure for brand risk" in content
        print("[OK] Registered new prohibited terminology rule", flush=True)

    # 5. TEST ADDING A PRODUCT FACT & SPEC
    post_fact = urllib.parse.urlencode({
        "product_name": "BrandShield Guard",
        "category": "Data Privacy",
        "feature_name": "Automated Regex + NER PII Masking",
        "specification_detail": "Scrubs emails, phone numbers, and SSNs in under 12ms before LLM evaluation.",
        "verified_source": "Privacy Architecture Specification v2.0",
        "confidentiality": "internal",
        "role": "reviewer"
    }).encode("utf-8")
    req = urllib.request.Request(f"{base_url}/brand-memory/facts/add", data=post_fact, method="POST")
    with urllib.request.urlopen(req, timeout=5) as resp:
        content = resp.read().decode("utf-8")
        assert "Automated Regex + NER PII Masking" in content
        print("[OK] Saved Product Fact with verified source documentation", flush=True)

    # 6. TEST CLAIMS GOVERNANCE: Adding Claim with Evidence & Verification Workflow
    # A) Creator proposes claim -> automatically marked PENDING_REVIEW
    post_claim_creator = urllib.parse.urlencode({
        "topic": "SOC3 Public Attestation",
        "claim_statement": "BrandShield holds verified SOC3 attestation for enterprise customers.",
        "evidence_type": "Public Audit Report",
        "source_reference": "EY SOC3 Report 2026",
        "review_date": str(date.today()),
        "role": "creator"
    }).encode("utf-8")
    req = urllib.request.Request(f"{base_url}/brand-memory/claims/add", data=post_claim_creator, method="POST")
    with urllib.request.urlopen(req, timeout=5) as resp:
        content = resp.read().decode("utf-8")
        assert "SOC3 Public Attestation" in content
        assert "PENDING LEGAL AUDIT" in content or "Pending" in content
        print("[OK] Arbitrary claim correctly forced to PENDING VERIFICATION status for creator", flush=True)

    # B) Reviewer verifies the pending claim
    with Session(engine) as s:
        claim_obj = s.exec(select(ApprovedClaim).where(ApprovedClaim.topic == "SOC3 Public Attestation")).first()
        assert claim_obj is not None
        claim_id = claim_obj.id

    post_verify = urllib.parse.urlencode({
        "status": "verified",
        "notes": "Verified against EY issued public seal.",
        "role": "reviewer"
    }).encode("utf-8")
    req = urllib.request.Request(f"{base_url}/brand-memory/claims/{claim_id}/verify", data=post_verify, method="POST")
    with urllib.request.urlopen(req, timeout=5) as resp:
        content = resp.read().decode("utf-8")
        assert "VERIFIED CLAIM" in content
        print("[OK] Reviewer successfully verified and approved the claim with audit trail", flush=True)

    # 7. TEST BRAND ASSET REFERENCE
    post_asset = urllib.parse.urlencode({
        "name": "BrandShield Secondary Emblem (Monochrome)",
        "category": "Logo",
        "usage_guidelines": "Use only on monochrome print collateral and official legal filings.",
        "attribution_text": "Codex 48 Registered Design.",
        "file_reference": "/static/brand/emblem_mono.svg",
        "role": "reviewer"
    }).encode("utf-8")
    req = urllib.request.Request(f"{base_url}/brand-memory/assets/add", data=post_asset, method="POST")
    with urllib.request.urlopen(req, timeout=5) as resp:
        content = resp.read().decode("utf-8")
        assert "Secondary Emblem" in content
        print("[OK] Added Brand Asset Reference and verified usage guidelines", flush=True)

    # 8. TEST RECORD DELETION
    req_del = urllib.request.Request(f"{base_url}/brand-memory/claims/{claim_id}/delete", data=urllib.parse.urlencode({"role": "reviewer"}).encode("utf-8"), method="POST")
    with urllib.request.urlopen(req_del, timeout=5) as resp:
        content = resp.read().decode("utf-8")
        assert "SOC3 Public Attestation" not in content
        print("[OK] Successfully deleted claim entry according to Reviewer permissions", flush=True)

    print("\n==========================================================================", flush=True)
    print("ALL 8 BRAND MEMORY GOVERNANCE & PERMISSION WORKFLOW TESTS PASSED 100%!", flush=True)
    print("==========================================================================", flush=True)

if __name__ == "__main__":
    run_brand_memory_tests()
