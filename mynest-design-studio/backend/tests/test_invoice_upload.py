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
    from fpdf import FPDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    
    # Add some text
    pdf.cell(0, 10, "INVOICE", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(5)
    pdf.cell(0, 10, "Invoice Number: INV-2024-001", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 10, "Date: 2024-01-15", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 10, "Vendor: ABC Supplies Ltd", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 10, "Customer: MyNest Studio", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    
    # Add a table
    pdf.set_font("Helvetica", "B", 10)
    col_widths = [40, 60, 30, 30]
    headers = ["Item", "Description", "Qty", "Price"]
    for i, h in enumerate(headers):
        pdf.cell(col_widths[i], 8, h, border=1)
    pdf.ln()
    
    pdf.set_font("Helvetica", "", 10)
    rows = [
        ["ITM-001", "Office Chair", "2", "150.00"],
        ["ITM-002", "Desk Lamp", "1", "45.00"],
        ["ITM-003", "Monitor Stand", "3", "35.00"],
    ]
    for row in rows:
        for i, cell in enumerate(row):
            pdf.cell(col_widths[i], 8, cell, border=1)
        pdf.ln()
    
    pdf.ln(5)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 10, "Subtotal: 630.00", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 10, "Tax (18%): 113.40", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 10, "Total: 743.40", new_x="LMARGIN", new_y="NEXT")
    
    return pdf.output()


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