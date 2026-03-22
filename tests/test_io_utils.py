from app.utils.io_utils import derive_run_path_from_source


def test_derive_run_path_from_webtoon_viewer_url() -> None:
    url = "https://www.webtoons.com/en/romance/dirty-deeds/episode-1/viewer?title_no=8808&episode_no=1"
    assert derive_run_path_from_source(url) == "romance/dirty-deeds/episode-1"


def test_derive_run_path_from_webtoon_list_url_with_episode_query() -> None:
    url = "https://www.webtoons.com/en/action/fog-land/list?title_no=123&episode_no=158"
    assert derive_run_path_from_source(url) == "action/fog-land/ep-158"


def test_derive_run_path_from_webtoon_viewer_url_without_episode_slug() -> None:
    url = "https://www.webtoons.com/en/action/fog-land/viewer?title_no=123&episode_no=171"
    assert derive_run_path_from_source(url) == "action/fog-land/ep-171"


def test_derive_run_id_from_non_webtoon_url() -> None:
    url = "https://example.com/some/path"
    assert derive_run_path_from_source(url) is None
