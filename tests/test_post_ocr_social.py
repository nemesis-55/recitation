from app.services.audio.post_ocr_narration import heuristic_clean_social_ui_text


def test_heuristic_drops_like_count_line():
    raw = "3 people like this post.\nI was walking home."
    assert "like this" not in heuristic_clean_social_ui_text(raw).lower()
    assert "walking" in heuristic_clean_social_ui_text(raw).lower()


def test_heuristic_drops_hashtag_only_block():
    assert heuristic_clean_social_ui_text("#foo #bar\nReal caption here.") == "Real caption here."


def test_heuristic_drops_share_comment():
    assert heuristic_clean_social_ui_text("Share\nHello there.") == "Hello there."
