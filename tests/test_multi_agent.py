from campusmind.agent.multi import SupervisorPlanner
from campusmind.agent.multi import HierarchicalMultiAgentService
from campusmind.agent.multi import AgentDomain, ChildAgentResult, MultiAgentTask


QUERY = "我快毕业了，帮我检查毕业条件，同时推荐两个AI方向老师，并找几本相关书。"


def test_supervisor_decomposes_three_domains():
    plan = SupervisorPlanner().plan(QUERY)
    assert [item.domain for item in plan.tasks] == [
        AgentDomain.ACADEMIC,
        AgentDomain.RESEARCH,
        AgentDomain.LIBRARY,
    ]
    assert plan.tasks[0].requires_actor is True
    assert all(item.write_intent is False for item in plan.tasks)
    assert plan.parallelizable is True


def test_supervisor_keeps_classroom_write_as_hitl_task():
    plan = SupervisorPlanner().plan("帮我预约2099-12-30下午可以坐30人的自习室。")
    assert len(plan.tasks) == 1
    task = plan.tasks[0]
    assert task.domain is AgentDomain.CAMPUS_SERVICE
    assert task.requires_actor is True
    assert task.write_intent is True
    assert plan.parallelizable is False


def test_supervisor_falls_back_to_general_knowledge():
    plan = SupervisorPlanner().plan("国家奖学金什么时候申请？")
    assert len(plan.tasks) == 1
    assert plan.tasks[0].domain is AgentDomain.GENERAL_KNOWLEDGE


def test_synthesis_marks_pending_approval():
    child = ChildAgentResult(
        task_id="task-1",
        domain=AgentDomain.CAMPUS_SERVICE,
        query="预约自习室",
        status="awaiting_approval",
        answer="找到候选教室，请确认。",
        source="agent_runtime:tool",
        pending_approval=True,
        approval_id="approval-1",
    )
    answer = HierarchicalMultiAgentService._synthesize([child], pending_approval=True)
    assert "找到候选教室" in answer
    assert "人工确认" in answer
    assert "/api/v1/agent/resume" in answer
