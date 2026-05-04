from app.models.confluence_page_cache import ConfluencePageCache


def test_model_has_expected_columns():
    cols = {c.name for c in ConfluencePageCache.__table__.columns}
    expected = {
        "id", "page_id", "source_url", "title",
        "body_text", "error", "fetched_at",
        "created_at", "updated_at",
    }
    assert expected <= cols
