from __future__ import annotations

import uuid

import pytest

from campusmind.agent.multi import ContextAwareExecutionCoordinator
from campusmind.agent.multi import AgentDomain, MultiAgentPlan, MultiAgentTask
from campusmind.platform.security import (
    AuthorizationDenied,
    AuthorizationService,
    StaticAuthorizationRepository,
)
from campusmind.platform.security import KnowledgeAclService


def _auth(roles=(), permissions=()):
    return AuthorizationService(
        None,
        repository=StaticAuthorizationRepository(roles=roles, permissions=permissions),
    )


def test_student_role_has_self_read_and_reservation_but_not_grade_update():
    actor = uuid.uuid4()
    service = _auth(roles={"student"})
    assert service.authorize("student.self.read", actor).allowed is True
    assert service.authorize("classroom.reserve", actor).allowed is True
    assert service.authorize("library.reserve", actor).allowed is True
    assert service.authorize("student.grade.update", actor).allowed is False
    assert service.authorize("audit.log.read", actor).allowed is False


def test_anonymous_can_read_public_catalogs_but_cannot_write():
    service = _auth()
    assert service.authorize("course.read").allowed is True
    assert service.authorize("research.read").allowed is True
    assert service.authorize("library.read").allowed is True
    assert service.authorize("classroom.reserve").allowed is False
    assert service.authorize("student.self.read").allowed is False


def test_explicit_database_permission_codes_are_additive():
    actor = uuid.uuid4()
    service = _auth(roles={"student"}, permissions={"document.upload"})
    assert service.authorize("document.upload", actor).allowed is True
    assert service.authorize("student.grade.update", actor).allowed is False


def test_knowledge_scope_is_role_bounded():
    actor = uuid.uuid4()
    student = KnowledgeAclService(None, authorization=_auth(roles={"student"}))
    scope = student.scope(actor)
    assert "public" in scope.permission_levels
    assert "campus" in scope.permission_levels
    assert "personal" in scope.permission_levels
    with pytest.raises(AuthorizationDenied):
        student.scope(actor, requested_levels=["admin"])

    anonymous = KnowledgeAclService(None, authorization=_auth())
    assert anonymous.scope().permission_levels == ["public"]


def test_secure_retrieval_passes_acl_before_call():
    actor = uuid.uuid4()
    acl = KnowledgeAclService(None, authorization=_auth(roles={"student"}))
    observed = {}

    def scoped_retriever(query: str, *, permission_levels):
        observed["levels"] = list(permission_levels)
        return f"ok:{query}"

    assert acl.secure_call(scoped_retriever, "q", actor_user_id=actor) == "ok:q"
    assert "campus" in observed["levels"]


def test_restricted_scope_refuses_legacy_retrieve_then_filter():
    actor = uuid.uuid4()
    acl = KnowledgeAclService(None, authorization=_auth(roles={"student"}))

    def legacy_retriever(query: str):
        return query

    with pytest.raises(AuthorizationDenied):
        acl.secure_call(legacy_retriever, "q", actor_user_id=actor)


def test_multi_agent_authorization_blocks_write_before_specialist_execution():
    calls = []

    class Registry:
        def run(self, task, *, actor_user_id=None, shared_context=None):
            calls.append(task.task_id)
            raise AssertionError("registry must not run for denied task")

    task = MultiAgentTask(
        task_id="task-1",
        domain=AgentDomain.CAMPUS_SERVICE,
        query="预约自习室",
        reason="test",
        requires_actor=True,
        write_intent=True,
    )
    plan = MultiAgentPlan(
        tasks=[task],
        parallelizable=False,
        supervisor_reason="test",
    )
    coordinator = ContextAwareExecutionCoordinator(Registry(), authorization=_auth())
    children, order, _ = coordinator.execute(plan, actor_user_id=None)
    assert calls == []
    assert order == ["task-1"]
    assert children[0].status == "deferred"
    assert children[0].source == "authorization"
    assert children[0].structured_data["side_effects"] == 0
