import os
from unittest.mock import MagicMock

from src.api.file_processor import FileWatcherHandler


def test_process_file_skips_vision_only_extensions(tmp_path):
    handler = FileWatcherHandler(str(tmp_path))
    handler._process_plaintext = MagicMock()
    handler.on_processed_callback = MagicMock()

    image_path = tmp_path / "diagram.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\n")

    handler.process_file(str(image_path))

    handler._process_plaintext.assert_not_called()
    handler.on_processed_callback.assert_not_called()
    assert not os.path.exists(os.path.join(handler.processed_dir, "diagram.png.txt"))
