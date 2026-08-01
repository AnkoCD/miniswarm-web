from pathlib import Path
from types import SimpleNamespace

from app.agent.runner_client import RunnerResult
from app.office_preview import office_preview_pdf


class FakeRunner:
    def __init__(self, root: Path):
        self.root = root
        self.calls = []

    def execute(self, **kwargs):
        self.calls.append(kwargs)
        target = self.root / kwargs["arguments"]["target"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"%PDF-1.4\n% preview\n")
        return RunnerResult(
            ok=True,
            summary="converted",
            data={"path": kwargs["arguments"]["target"]},
        )


def test_office_preview_uses_runner_and_private_cache(tmp_path):
    source = tmp_path / "output" / "paper_1" / "exam.docx"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"PK\x03\x04fake-docx")
    task = SimpleNamespace(owner_id="user-1", id="task-1")
    artifact = SimpleNamespace(
        id="artifact-1",
        filename="exam.docx",
        relative_path="output/paper_1/exam.docx",
    )
    runner = FakeRunner(tmp_path)

    rendered = office_preview_pdf(
        task,
        artifact,
        source,
        runner=runner,
        root=tmp_path,
    )

    assert rendered == tmp_path / "workspace/.previews/artifact-1/preview.pdf"
    assert rendered.read_bytes().startswith(b"%PDF-")
    assert runner.calls[0]["tool"] == "convert_document"
    assert runner.calls[0]["approval_granted"] is True

    rendered_again = office_preview_pdf(
        task,
        artifact,
        source,
        runner=runner,
        root=tmp_path,
    )
    assert rendered_again == rendered
    assert len(runner.calls) == 1


def test_invalid_preview_cache_is_not_reused(tmp_path):
    source = tmp_path / "output" / "paper_1" / "exam.docx"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"PK\x03\x04fake-docx")
    task = SimpleNamespace(owner_id="user-1", id="task-1")
    artifact = SimpleNamespace(
        id="artifact-1",
        filename="exam.docx",
        relative_path="output/paper_1/exam.docx",
    )
    invalid = tmp_path / "workspace/.previews/artifact-1/preview.pdf"
    invalid.parent.mkdir(parents=True)
    invalid.write_bytes(b"not-a-pdf")
    runner = FakeRunner(tmp_path)

    rendered = office_preview_pdf(task, artifact, source, runner=runner, root=tmp_path)

    assert rendered.read_bytes().startswith(b"%PDF-")
    assert len(runner.calls) == 1
