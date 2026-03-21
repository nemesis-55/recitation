from app.utils.io_utils import derive_run_path_from_source


def test_derive_run_path_from_webtoon_viewer_url() -> None:
    url = "https://www.webtoons.com/en/romance/dirty-deeds/episode-1/viewer?title_no=8808&episode_no=1"
    assert derive_run_path_from_source(url) == "romance/dirty-deeds/episode-1"


def test_derive_run_id_from_non_webtoon_url() -> None:
    url = "https://example.com/some/path"
    assert derive_run_path_from_source(url) is None
