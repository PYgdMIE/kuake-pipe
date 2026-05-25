"""Test the input validation helper in commands/init.py."""
from unittest.mock import patch
import builtins
from kuake.commands.init import _prompt_index


def test_prompt_index_valid(monkeypatch):
    """Direct valid input."""
    from rich.prompt import Prompt
    with patch.object(Prompt, "ask", side_effect=["2"]):
        assert _prompt_index("pick", n=5) == 1


def test_prompt_index_default(monkeypatch):
    """Default returns 0 (first item)."""
    from rich.prompt import Prompt
    with patch.object(Prompt, "ask", side_effect=["1"]):
        assert _prompt_index("pick", n=3) == 0


def test_prompt_index_retry_on_nonnumeric(monkeypatch):
    """Loops on non-numeric, eventually accepts valid."""
    from rich.prompt import Prompt
    with patch.object(Prompt, "ask", side_effect=["abc", "2"]):
        assert _prompt_index("pick", n=5) == 1


def test_prompt_index_retry_on_out_of_range(monkeypatch):
    from rich.prompt import Prompt
    with patch.object(Prompt, "ask", side_effect=["10", "0", "3"]):
        assert _prompt_index("pick", n=5) == 2
