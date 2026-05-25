"""Unit-level tests for selector table sanity.
Real DOM matching is covered in MANUAL_TEST.md."""
from kuake.browser.selectors import (
    AUTODL_INSTANCE_ROW, AUTODL_LOGGED_IN, AUTODL_INSTANCE_SSH,
    AUTODL_INSTANCE_PASSWORD, AUTODL_AUTOPANEL_LINK,
    QUARK_LOGGED_IN, QUARK_BACKUP_FOLDER,
    AUTOPANEL_API_PATTERN,
    SelectorSet,
)


def test_all_selector_sets_have_fallback():
    """Every SelectorSet must have ≥2 strategies for resilience."""
    sets = [
        AUTODL_INSTANCE_ROW, AUTODL_LOGGED_IN,
        AUTODL_INSTANCE_SSH, AUTODL_INSTANCE_PASSWORD, AUTODL_AUTOPANEL_LINK,
        QUARK_LOGGED_IN, QUARK_BACKUP_FOLDER,
    ]
    for s in sets:
        assert len(s.strategies) >= 2, f"{s.name} has <2 strategies"


def test_selectors_have_names():
    assert AUTODL_INSTANCE_ROW.name == "autodl_instance_row"
    assert QUARK_BACKUP_FOLDER.name == "quark_backup_folder"


def test_autopanel_api_pattern_is_glob():
    assert "/autopanel/" in AUTOPANEL_API_PATTERN
    assert "*" in AUTOPANEL_API_PATTERN


def test_selector_set_immutability():
    """SelectorSet is frozen dataclass."""
    import pytest
    with pytest.raises(Exception):
        AUTODL_INSTANCE_ROW.strategies = ("changed",)
