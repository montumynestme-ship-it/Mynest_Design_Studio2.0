import pytest
from pathlib import Path
import io
from fastapi.testclient import TestClient

from app.main import app
from app.db.base import init_db, session_scope
from app.db.models import Invoice, InvoiceColumn, InvoiceRow
from app.storage.file_storage import ensure_storage_ready


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    ensure_storage_ready()
    init_db()
    yield
    with session_scope() as db:
        db.query(Invoice).delete()
        db.query(InvoiceColumn).delete()
        db.query(InvoiceRow).delete()


def create_sample_pdf() -> bytes:
    """Create a simple test PDF with a table for testing."""
    from io import BytesIO
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter)
    styles = getSampleStyleSheet()

    story = [
        Paragraph("INVOICE", styles["Title"]),
        Spacer(1, 5),
        Paragraph("Invoice Number: INV-2024-001", styles["Normal"]),
        Paragraph("Date: 2024-01-15", styles["Normal"]),
        Paragraph("Vendor: ABC Supplies Ltd", styles["Normal"]),
        Paragraph("Customer: MyNest Studio", styles["Normal"]),
        Spacer(1, 10),
        Table(
            [
                ["Item", "Description", "Qty", "Price"],
                ["ITM-001", "Office Chair", "2", "150.00"],
                ["ITM-002", "Desk Lamp", "1", "45.00"],
                ["ITM-003", "Monitor Stand", "3", "35.00"],
            ],
            style=[
                ("GRID", (0, 0), (-1, -1), 1, colors.black),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ],
        ),
        Spacer(1, 10),
        Paragraph("Subtotal: 630.00", styles["Normal"]),
        Paragraph("Tax (18%): 113.40", styles["Normal"]),
        Paragraph("Total: 743.40", styles["Normal"]),
    ]
    doc.build(story)
    return buf.getvalue()


def test_upload_invoice_pdf(setup_db):
    client = TestClient(app)
    
    pdf_bytes = create_sample_pdf()
    files = {"file": ("test_invoice.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    
    response = client.post("/api/invoices/upload", files=files)
    assert response.status_code == 201
    
    data = response.json()
    assert data["original_filename"] == "test_invoice.pdf"
    assert data["status"] == "processed"
    assert data["raw_data"] is not None
    
    invoice_id = data["id"]
    
    # Check detail endpoint
    detail_resp = client.get(f"/api/invoices/{invoice_id}/detail")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    
    assert len(detail["columns"]) > 0
    assert len(detail["rows"]) > 0
    
    # Verify column names extracted from table
    column_names = [c["name"] for c in detail["columns"]]
    assert "Item" in column_names
    assert "Description" in column_names
    assert "Qty" in column_names
    assert "Price" in column_names
    
    # Verify rows extracted
    assert len(detail["rows"]) == 3
    
    # Check field mapping suggestions
    suggestions_resp = client.get(f"/api/invoices/{invoice_id}/field-mapping-suggestions")
    assert suggestions_resp.status_code == 200
    suggestions = suggestions_resp.json()
    assert len(suggestions) > 0
    
    # Verify some standard fields were suggested
    suggested_fields = [s["suggested_target_field"] for s in suggestions if s["suggested_target_field"]]
    # "Item" column should match "line_items" standard field
    assert "line_items" in suggested_fields


def test_list_invoices(setup_db):
    client = TestClient(app)
    response = client.get("/api/invoices")
    assert response.status_code == 200
    data = response.json()
    assert "invoices" in data
    assert "total" in data


def test_delete_invoice(setup_db):
    client = TestClient(app)
    
    pdf_bytes = create_sample_pdf()
    files = {"file": ("test_delete.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    upload_resp = client.post("/api/invoices/upload", files=files)
    invoice_id = upload_resp.json()["id"]
    
    delete_resp = client.delete(f"/api/invoices/{invoice_id}")
    assert delete_resp.status_code == 200
    
    get_resp = client.get(f"/api/invoices/{invoice_id}")
    assert get_resp.status_code == 404


if __name__ == "__main__":
    pytest.main([__file__, "-v"])