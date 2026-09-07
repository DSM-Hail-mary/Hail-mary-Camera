from Hail_Mary.vision import preview


def test_preview_module_imports_cleanly_and_exposes_main():
    assert callable(preview.main)
    assert preview.WINDOW_NAME == "Hail-Mary YOLOv8n preview"
