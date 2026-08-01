from app.core.config import Settings
from app.db import SessionLocal
from app.models import (
    Artifact,
    NodeStatus,
    Task,
    TaskNode,
    TaskStatus,
    ToolCall,
    ToolCallStatus,
    User,
)
from app.quality import (
    _artifact_source_domains,
    is_requested_delivery_artifact,
    mark_verified_artifacts,
    requested_formats,
    source_requirements,
    validate_delivery,
)
from app.storage import task_root


def _settings(tmp_path):
    return Settings(
        app_env="test",
        jwt_secret="test-secret-that-is-long-enough",
        data_root=tmp_path,
    )


def test_delivery_gate_requires_requested_format_and_reviewer_inspection(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    monkeypatch.setattr("app.quality.get_settings", lambda: settings)
    with SessionLocal() as db:
        user = db.query(User).filter_by(username="admin").one()
        task = Task(
            owner_id=user.id,
            title="制作演示",
            prompt="制作一份 PPTX 演示文稿",
            task_type="document",
            status=TaskStatus.REVIEWING,
        )
        db.add(task)
        db.flush()
        producer = TaskNode(
            task_id=task.id, node_key="work", role="document", title="生成 PPTX",
            instructions="生成文件", depends_on=[], weight=80, status=NodeStatus.SUCCEEDED,
        )
        reviewer = TaskNode(
            task_id=task.id, node_key="review", role="reviewer", title="检查 PPTX",
            instructions="检查文件", depends_on=["work"], weight=20, status=NodeStatus.SUCCEEDED,
        )
        db.add_all([producer, reviewer])
        db.flush()
        output = task_root(task.owner_id, task.id, settings) / "output" / "report.pptx"
        output.write_bytes(b"verified-by-runner-in-real-execution")
        artifact = Artifact(
            task_id=task.id, node_id=producer.id, filename="report.pptx",
            relative_path="output/report.pptx", size=output.stat().st_size,
            is_final=True, inspection_status="READY",
        )
        db.add(artifact)
        db.commit()

        first = validate_delivery(db, task, [producer, reviewer])
        assert not first.passed
        assert "Reviewer 尚未逐一检查" in first.summary

        db.add(
            ToolCall(
                task_id=task.id, node_id=reviewer.id, tool_name="inspect_document",
                arguments={"path": "output/report.pptx"}, status=ToolCallStatus.SUCCEEDED,
            )
        )
        db.commit()
        second = validate_delivery(db, task, [producer, reviewer])
        assert second.passed
        mark_verified_artifacts(db, task.id, second.verified_paths)
        assert artifact.inspection_status == "VERIFIED"


def test_delivery_gate_rejects_wrong_explicit_format(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    monkeypatch.setattr("app.quality.get_settings", lambda: settings)
    with SessionLocal() as db:
        user = db.query(User).filter_by(username="admin").one()
        task = Task(
            owner_id=user.id, title="报告", prompt="生成 PDF 报告",
            task_type="document", status=TaskStatus.REVIEWING,
        )
        db.add(task)
        db.flush()
        reviewer = TaskNode(
            task_id=task.id, node_key="review", role="reviewer", title="检查",
            instructions="检查", depends_on=[], weight=100, status=NodeStatus.SUCCEEDED,
        )
        db.add(reviewer)
        db.commit()
        result = validate_delivery(db, task, [reviewer])
        assert "用户要求 PDF" in result.summary


def test_requested_formats_ignore_explicitly_rejected_alternative():
    formats = dict(requested_formats("生成 PPTX，不要生成 HTML 替代品，也不需要 PDF"))
    assert "PPTX" in formats
    assert "HTML" not in formats
    assert "PDF" not in formats
    assert dict(requested_formats("生成 DOCX，不要生成 PDF 或 HTML 替代品")) == {
        "DOCX": (".docx",)
    }
    assert set(dict(requested_formats("不要只生成 PDF 但要生成 HTML"))) == {"HTML"}
    assert dict(
        requested_formats(
            "完成中文深度调研报告，主题为“Word、Excel 与 PDF 自动化交付的质量保障方法”，"
            "最终文件必须命名为 output/quality-eval-office-research.docx"
        )
    ) == {"DOCX": (".docx",)}


def test_requested_formats_choose_office_defaults_when_unspecified():
    assert dict(requested_formats("编写一份季度总结报告"))["DOCX"] == (".docx",)
    assert dict(requested_formats("制作一份项目跟踪表"))["XLSX"] == (".xlsx", ".xlsm")
    assert set(dict(requested_formats("制作季度总结报告 PPTX"))) == {"PPTX"}


def test_only_requested_format_is_required_delivery_artifact():
    prompt = "联网制作“当今AI发展趋势”7页PPT"
    assert is_requested_delivery_artifact(prompt, "AI发展趋势.pptx")
    assert not is_requested_delivery_artifact(prompt, "AI发展趋势.pdf")
    assert is_requested_delivery_artifact("整理这些文件", "notes.pdf")


def test_source_requirements_scale_with_research_depth():
    assert source_requirements("整理现有文件") == (0, 0, False)
    assert source_requirements("联网检索资料并制作报告") == (2, 2, True)
    assert source_requirements("制作最新新闻摘要") == (2, 2, False)
    assert source_requirements("完成一份深度调研报告") == (4, 3, True)


def test_artifact_source_domains_detects_embedded_urls(tmp_path):
    report = tmp_path / "report.md"
    report.write_text(
        "来源：https://example.com/report\n来源：https://official.test/data",
        encoding="utf-8",
    )
    assert _artifact_source_domains(
        report, {"example.com", "official.test", "missing.test"}
    ) == {"example.com", "official.test"}
