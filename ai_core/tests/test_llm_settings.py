from admin_panel.settings import AgentSettings
from ai_core.graph import builder


def test_vertex_location_from_admin_is_passed_to_primary_model(
    monkeypatch,
) -> None:
    captured = {}

    def fake_google_model(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/tmp/test-credentials.json")
    monkeypatch.setattr(builder, "ChatGoogleGenerativeAI", fake_google_model)

    builder.build_llm(
        AgentSettings(
            provider="google_vertex",
            model="gemini-3.5-flash-lite",
            vertex_location="global",
        )
    )

    assert captured["model"] == "gemini-3.5-flash-lite"
    assert captured["location"] == "global"


def test_vertex_location_from_admin_is_passed_to_separate_rag_model(
    monkeypatch,
) -> None:
    captured = {}

    def fake_google_model(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/tmp/test-credentials.json")
    monkeypatch.setenv("RAG_EXTRACTOR_LLM_PROVIDER", "google_vertex")
    monkeypatch.setattr(builder, "ChatGoogleGenerativeAI", fake_google_model)

    builder.build_rag_extractor_llm(object(), vertex_location="eu")

    assert captured["location"] == "eu"
