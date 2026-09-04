from millet_news.config import load_all
from millet_news.pipeline import Pipeline


def test_end_to_end_mock_never_calls_network_or_instagram(tmp_path, monkeypatch):
    config = load_all()
    config["output_dir"] = str(tmp_path / "output")
    monkeypatch.setattr("millet_news.pipeline.FeedCollector.collect", lambda self, sources, search_terms=None: [])
    result = Pipeline(config, tmp_path / "pipeline.db").run("automatic", mock_generation=True, mock_publish=True)
    assert result["status"] == "published"
