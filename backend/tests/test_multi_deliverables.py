from app.agent.deliverables import detect_multi_deliverable_request
from app.agent.planner import Planner, TaskPlan


def _single_exam_plan() -> TaskPlan:
    return TaskPlan.model_validate(
        {
            "mode": "single",
            "goal": "生成三套试卷",
            "acceptance_criteria": ["文件可打开"],
            "nodes": [
                {
                    "id": "make_exam",
                    "role": "document",
                    "title": "生成试卷",
                    "instructions": "生成三套初中物理试卷",
                    "depends_on": [],
                    "weight": 80,
                },
                {
                    "id": "review",
                    "role": "reviewer",
                    "title": "检查试卷",
                    "instructions": "检查全部试卷",
                    "depends_on": ["make_exam"],
                    "weight": 20,
                },
            ],
        }
    )


def test_detects_explicit_multi_deliverable_request():
    detected = detect_multi_deliverable_request("生成三套不同的初中物理试卷")
    assert detected is not None
    assert detected.count == 3
    assert detected.noun == "试卷"


def test_does_not_split_chapters_of_one_report():
    assert detect_multi_deliverable_request("生成一份包含三个章节的报告") is None


def test_single_exam_worker_expands_to_three_parallel_workers():
    plan = _single_exam_plan()
    Planner._expand_multi_deliverables("生成三套不同的初中物理试卷", plan)
    validated = TaskPlan.model_validate(plan.model_dump())
    workers = [node for node in validated.nodes if node.role != "reviewer"]
    assert validated.mode == "swarm"
    assert len(workers) == 3
    assert validated.nodes[-1].depends_on == [node.id for node in workers]
    assert all(f"output/{node.id}/" in node.instructions for node in workers)


def test_shared_dependency_is_kept_for_each_copy():
    plan = TaskPlan.model_validate(
        {
            "mode": "single",
            "goal": "研究范围后生成三套试卷",
            "nodes": [
                {
                    "id": "research",
                    "role": "researcher",
                    "title": "整理命题范围",
                    "instructions": "读取资料并整理统一命题范围",
                    "depends_on": [],
                    "weight": 20,
                },
                {
                    "id": "make_exam",
                    "role": "document",
                    "title": "生成试卷",
                    "instructions": "根据统一范围生成试卷",
                    "depends_on": ["research"],
                    "weight": 60,
                },
                {
                    "id": "review",
                    "role": "reviewer",
                    "title": "检查试卷",
                    "instructions": "检查全部试卷",
                    "depends_on": ["make_exam"],
                    "weight": 20,
                },
            ],
        }
    )
    Planner._expand_multi_deliverables("生成三套不同的初中物理试卷", plan)
    exams = [node for node in plan.nodes if node.id.startswith("make_exam_")]
    assert len(exams) == 3
    assert all(node.depends_on == ["research"] for node in exams)


def test_terminal_document_is_selected_when_prompt_noun_differs_from_node_wording():
    plan = TaskPlan.model_validate(
        {
            "mode": "single",
            "goal": "研究后制作三份 PPT",
            "nodes": [
                {
                    "id": "research",
                    "role": "researcher",
                    "title": "整理资料",
                    "instructions": "整理演示所需资料",
                    "depends_on": [],
                    "weight": 20,
                },
                {
                    "id": "slides",
                    "role": "document",
                    "title": "制作演示文稿",
                    "instructions": "制作真实幻灯片文件",
                    "depends_on": ["research"],
                    "weight": 60,
                },
                {
                    "id": "review",
                    "role": "reviewer",
                    "title": "检查演示文稿",
                    "instructions": "逐份检查",
                    "depends_on": ["slides"],
                    "weight": 20,
                },
            ],
        }
    )
    Planner._expand_multi_deliverables("制作三份不同的 PPT", plan)
    slides = [node for node in plan.nodes if node.id.startswith("slides_")]
    assert len(slides) == 3
