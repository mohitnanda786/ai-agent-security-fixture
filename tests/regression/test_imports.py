from src.scoring import clamp_score


def test_module_exposes_clamp_score():
    assert callable(clamp_score)
