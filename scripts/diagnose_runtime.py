from __future__ import annotations

import json
from dataclasses import asdict

from campusmind.config import get_settings
from campusmind.platform.db import get_session_factory
from campusmind.knowledge.adaptive import AdaptiveRagService
from campusmind.knowledge.graph_rag import GraphRagService

QUERIES = [
    "机器学习课程有哪些先修要求？",
    "当前知识图谱中，从课程「数据结构」沿 PREREQUISITE_OF 正向一跳会到达哪门课程？",
    "哪些课程通过 PREREQUISITE_OF 指向课程「机器学习」？",
]

def main() -> None:
    settings = get_settings()
    print(f"CampusMind runtime diagnostic · {settings.app_version}")
    factory = get_session_factory()
    with factory() as session:
        adaptive = AdaptiveRagService(session)
        graph = GraphRagService(session)
        try:
            for query in QUERIES:
                print("\n" + "=" * 90)
                print("QUERY:", query)
                decision = adaptive.route(query)
                print("ROUTE:", decision.route.value, decision.intent, decision.complexity, decision.confidence)
                if decision.route.value == "graph":
                    search = graph.search(query)
                    print("PLAN:", search.plan.model_dump(mode="json"))
                    print("LINKED:", [item.name for item in search.linked_entities])
                    print("RAW_PATHS:", search.raw_path_count)
                    print("VERIFIED_PATHS:", [item.path_text for item in search.paths])
                    print("CITATIONS:", len(search.evidence_hits))
                    print("RECOVERED_EVIDENCE:", search.recovered_evidence_count)
                    print("DIAGNOSTICS:", list(search.diagnostics))
        finally:
            adaptive.close()
            graph.close()

if __name__ == "__main__":
    main()
