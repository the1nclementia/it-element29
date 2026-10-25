import uuid

from app.modules.identity.repository import audit


class AuditSession:
    def add(self, record):
        self.record = record


def test_catalog_audit_preserves_field_names_without_values_or_secrets():
    session = AuditSession()
    audit(
        session,
        uuid.uuid4(),
        "inventory.item_updated",
        uuid.uuid4(),
        {
            "fields": ["model", "min_stock"],
            "description": "PRIVATE VALUE",
            "password": "SECRET",
        },
    )
    assert session.record.changes == {"fields": ["model", "min_stock"]}


def test_compatibility_audit_preserves_only_valid_model_identifiers():
    session = AuditSession()
    model_id = str(uuid.uuid4())
    audit(
        session,
        uuid.uuid4(),
        "inventory.compatibilities_updated",
        uuid.uuid4(),
        {"printer_model_ids": [model_id, "SECRET"], "fields": ["password", "model"]},
    )
    assert session.record.changes == {
        "printer_model_ids": [model_id],
        "fields": ["model"],
    }
