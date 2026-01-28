import pytest
from playwright.sync_api import Page, expect

# Assumption: The app is running on localhost:3000
BASE_URL = "http://localhost:3000"

@pytest.mark.skip(reason="Requires running frontend and backend")
def test_tenant_ingest_search_flow(page: Page):
    # 1. Create Tenant
    page.goto(f"{BASE_URL}/admin/tenants")
    page.get_by_placeholder("Tenant Name").fill("e2e-tenant")
    page.get_by_role("button", name="Create").click()
    expect(page.get_by_text("e2e-tenant")).to_be_visible()

    # 2. Ingest Code
    page.goto(f"{BASE_URL}/admin/ingestion")
    page.get_by_placeholder("https://github.com/...").fill("https://github.com/ArtisanClarinets/jules_rag")
    # Set collection - finding by value or surrounding text
    # Assuming the first collection input is for code
    page.locator("input").filter({ has_text: "test_collection" }).first.fill("e2e_collection")
    page.get_by_role("button", name="Start Ingestion").click()
    expect(page.get_by_text("Ingestion queued!")).to_be_visible()

    # 3. Search
    page.goto(f"{BASE_URL}/")
    page.get_by_placeholder("Enter query...").fill("RAG")
    # Set collection
    page.locator("input[value='test_collection']").fill("e2e_collection")
    page.get_by_role("button", name="Search").click()
    # Expect some result or no error
    # expect(page.get_by_text("Result 1")).to_be_visible()

def test_doc_ingestion_elements(page: Page):
    page.goto(f"{BASE_URL}/admin/ingestion")
    expect(page.get_by_text("Document Ingestion")).to_be_visible()
    expect(page.get_by_text("Upload & Ingest")).to_be_disabled()

def test_settings_persistence(page: Page):
    page.goto(f"{BASE_URL}/admin/settings")

    # Add new setting
    page.get_by_placeholder("Key").fill("test_key")
    page.get_by_placeholder("Value").fill("test_val")
    page.get_by_role("button", name="Add").click()

    expect(page.get_by_text("test_key")).to_be_visible()
    expect(page.get_by_display_value("test_val")).to_be_visible()

    # Save
    page.get_by_role("button", name="Save Changes").click()
    expect(page.get_by_text("Saved!")).to_be_visible()

    # Reload
    page.reload()
    expect(page.get_by_text("test_key")).to_be_visible()
