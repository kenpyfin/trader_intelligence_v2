"""Keep GPT prompt overrides from hitting live Mongo during unit tests."""
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def isolate_prompt_overrides():
    mock_col = MagicMock()
    mock_col.find.return_value = []
    with patch("src.services.prompt_config_service._get_collection", return_value=mock_col):
        try:
            from src.services.prompt_config_service import reset_prompt_cache
        except Exception:
            yield mock_col
            return
        reset_prompt_cache()
        yield mock_col
        reset_prompt_cache()
