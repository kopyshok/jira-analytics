# Lazy Tree on `/categories` — Этап 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Дерево `/categories` для любой команды (включая 1С/ERP с 6000+ задач) грузится за ~1 с, клики по чекбоксам/Select мгновенные, память O(видимых узлов) вместо O(всего дерева).

**Architecture:** Сервер отдаёт сначала только корневые узлы текущей вкладки (с метаданными `has_children` + `descendant_count` + `descendant_match_count`), потомки тянутся по `onExpand` отдельным запросом. Тяжёлые walk-меморы (`buildTabData`, `descendantCounts`, `epicCandidates`) переезжают на сервер. Старый `/issues/tree` endpoint остаётся (другие модули могут использовать), но `CategoriesEditorPage` его больше не дергает.

**Tech Stack:** Backend — FastAPI + SQLAlchemy 2.0 ORM; Frontend — React 19 + TanStack Query + AntD 6 (`Table` tree-mode с `expandable.loadData`).

---

## File Structure

**Backend:**
- Modify: `app/api/endpoints/issue_config.py` — добавить 4 новых эндпоинта рядом с существующим `/tree`:
  - `GET /issues/tree/roots` — корневые узлы вкладки
  - `GET /issues/tree/counts` — счётчики по вкладкам
  - `GET /issues/tree/epic-candidates` — список эпиков с категорией и >0 детей (для Cascade-секции drawer'а)
  - Extend `GET /issues/{id}/children` — добавить параметры `tab` + `pending_categories` (optional JSON map) для tab-фильтра при ленивом раскрытии
- Modify: `app/services/category_resolver.py` — вынести helper `effective_category_with_ancestors(issue, pending_overrides)` если ещё нет; используется обоими endpoint'ами для определения, в какую вкладку попадает узел
- Test: `tests/test_issue_tree_lazy_endpoints.py` — новый файл, тесты на 4 эндпоинта

**Frontend:**
- Create: `frontend/src/hooks/useIssueLazyTree.ts` — четыре новых хука (`useIssueRoots`, `useIssueChildren`, `useIssueTreeCounts`, `useEpicCandidates`)
- Modify: `frontend/src/api/issues.ts` — добавить API-обёртки для новых эндпоинтов
- Modify: `frontend/src/types/api.ts` — добавить типы (`IssueRootNode`, `IssueTreeCounts`, `EpicCandidate`)
- Modify: `frontend/src/pages/CategoriesEditorPage.tsx` — большая переработка:
  - Заменить `useIssueTree` → `useIssueRoots` + `useIssueChildren`
  - Удалить локальные walks (`buildTabData`, `descendantCounts`, `nodeById`, `epicCandidates`, `countTriage`, `uniqueStatuses`)
  - Добавить state `loadedChildrenByParent: Map<string, IssueTreeNode[]>` + `onExpand` handler
  - Поиск — debounced, передаётся в `useIssueRoots`
  - «Развернуть всё» → дизейблим (показываем подсказку «недоступно для больших деревьев»)
- Modify: `frontend/src/components/categories/sections/BulkCascadeInheritSection.tsx` — принимать `candidates` из нового хука `useEpicCandidates`, а не от родителя
- Modify: `frontend/src/components/categories/BulkTriageDrawer.tsx` — убрать prop `epicCandidates` (секция берёт из хука)

**Принципы декомпозиции:**
- Backend: все новые endpoint'ы в `issue_config.py` рядом с существующим `/tree` — пользователь читает один файл для понимания tree-логики
- Frontend: новые хуки в отдельном файле, чтобы `useIssueTree` (используется другими страницами) не трогать
- Page-rewrite — одна задача, потому что все walks связаны и переделка по одному — мёртвый код в середине

---

## Task 1: Backend — `effective_category_with_ancestors` helper

**Files:**
- Modify: `app/services/category_resolver.py`
- Test: `tests/test_category_resolver_effective_with_ancestors.py` (новый)

- [ ] **Step 1: Падающий тест**

```python
"""Тесты helper для определения эффективной категории с учётом предков."""
import pytest
from app.database import SessionLocal
from app.models import Issue, Project
from app.services.category_resolver import CategoryResolver, effective_category_with_ancestors


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _mk_proj(db, key):
    p = Project(id=f"proj-{key}", key=key, name=key, jira_id=f"j-{key}")
    db.add(p); db.flush()
    return p


def _mk_issue(db, proj, key, **overrides):
    defaults = dict(
        id=f"i-{key}", key=key, summary=key,
        issue_type="Task", status="Открыто",
        project_id=proj.id, jira_id=f"j-{key}",
        category_verified=True, include_in_analysis=True,
    )
    defaults.update(overrides)
    i = Issue(**defaults); db.add(i); db.flush()
    return i


def test_own_assigned_wins(db):
    p = _mk_proj(db, "EFF1")
    epic = _mk_issue(db, p, "EFF1-1", issue_type="Epic", assigned_category="support")
    child = _mk_issue(db, p, "EFF1-2", parent_id=epic.id, assigned_category="dev")
    db.commit()
    try:
        resolver = CategoryResolver(db)
        result = effective_category_with_ancestors(resolver, child, pending={})
        assert result == "dev"
    finally:
        db.query(Issue).filter(Issue.project_id == p.id).delete()
        db.query(Project).filter(Project.id == p.id).delete()
        db.commit()


def test_inherited_from_ancestor(db):
    p = _mk_proj(db, "EFF2")
    epic = _mk_issue(db, p, "EFF2-1", issue_type="Epic", assigned_category="support")
    child = _mk_issue(db, p, "EFF2-2", parent_id=epic.id, assigned_category=None)
    db.commit()
    try:
        resolver = CategoryResolver(db)
        result = effective_category_with_ancestors(resolver, child, pending={})
        assert result == "support"
    finally:
        db.query(Issue).filter(Issue.project_id == p.id).delete()
        db.query(Project).filter(Project.id == p.id).delete()
        db.commit()


def test_pending_overrides_assigned(db):
    p = _mk_proj(db, "EFF3")
    issue = _mk_issue(db, p, "EFF3-1", assigned_category="dev")
    db.commit()
    try:
        resolver = CategoryResolver(db)
        result = effective_category_with_ancestors(resolver, issue, pending={issue.id: "qa"})
        assert result == "qa"
    finally:
        db.query(Issue).filter(Issue.project_id == p.id).delete()
        db.query(Project).filter(Project.id == p.id).delete()
        db.commit()


def test_returns_none_for_unverified(db):
    p = _mk_proj(db, "EFF4")
    issue = _mk_issue(db, p, "EFF4-1", assigned_category=None, category_verified=False)
    db.commit()
    try:
        resolver = CategoryResolver(db)
        result = effective_category_with_ancestors(resolver, issue, pending={})
        assert result is None
    finally:
        db.query(Issue).filter(Issue.project_id == p.id).delete()
        db.query(Project).filter(Project.id == p.id).delete()
        db.commit()
```

- [ ] **Step 2: Run — FAIL**

`py -3.10 -m pytest tests/test_category_resolver_effective_with_ancestors.py -v`

- [ ] **Step 3: Implement helper**

Append to `app/services/category_resolver.py`:

```python
def effective_category_with_ancestors(
    resolver: "CategoryResolver",
    issue: "Issue",
    pending: dict[str, str | None],
) -> str | None:
    """Вернуть эффективную категорию задачи: pending override → own assigned → ближайший
    предок с assigned_category. Используется server-side для tab-routing задач.

    pending — клиентский патч {issue_id: category_code | None}. Передаётся
    фронтом в запрос tree/roots, чтобы клик «Сохранить» не требовал refetch.
    """
    from app.models import Issue  # local import to avoid circular
    sess = resolver.db

    if issue.id in pending:
        own = pending[issue.id]
        if own is not None:
            return own
        # pending=null означает «снять категорию» — пусть наследуется от предков

    if not (issue.category_verified or False):
        return None  # «К разбору»

    if issue.assigned_category:
        return issue.assigned_category

    # walk up по parent_id, max 20 шагов (cycle guard)
    current_parent_id = issue.parent_id
    for _ in range(20):
        if not current_parent_id:
            return None
        # pending на предке тоже учитываем
        if current_parent_id in pending:
            return pending[current_parent_id]
        parent = sess.get(Issue, current_parent_id)
        if not parent:
            return None
        if parent.assigned_category:
            return parent.assigned_category
        current_parent_id = parent.parent_id
    return None
```

- [ ] **Step 4: Run — PASS (4 tests)**

`py -3.10 -m pytest tests/test_category_resolver_effective_with_ancestors.py -v`

- [ ] **Step 5: Commit**

```bash
git add app/services/category_resolver.py tests/test_category_resolver_effective_with_ancestors.py
git commit -m "feat(categories): effective_category_with_ancestors helper для tab-routing"
```

---

## Task 2: Backend — `/issues/tree/counts` endpoint

**Files:**
- Modify: `app/api/endpoints/issue_config.py` (добавить endpoint)
- Test: `tests/test_issue_tree_lazy_endpoints.py` (новый файл)

- [ ] **Step 1: Падающий тест**

```python
"""Тесты ленивых tree-эндпоинтов для CategoriesEditorPage."""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app.models import Issue, Project


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _mk_proj(db, key="LZY"):
    p = Project(id=f"proj-{key}", key=key, name=key, jira_id=f"j-{key}")
    db.add(p); db.flush()
    return p


def _mk_issue(db, proj, key, **overrides):
    defaults = dict(
        id=f"i-{key}", key=key, summary=key,
        issue_type="Task", status="Открыто",
        project_id=proj.id, jira_id=f"j-{key}",
        category_verified=True, include_in_analysis=True,
    )
    defaults.update(overrides)
    i = Issue(**defaults); db.add(i); db.flush()
    return i


def test_tree_counts_groups_by_tab(client, db):
    p = _mk_proj(db, "CNT")
    _mk_issue(db, p, "CNT-1", assigned_category=None, category_verified=False)  # stack
    _mk_issue(db, p, "CNT-2", assigned_category="dev")  # active
    _mk_issue(db, p, "CNT-3", assigned_category="initiatives_rfa")  # initiatives
    _mk_issue(db, p, "CNT-4", assigned_category="archive_target")  # archive_target
    _mk_issue(db, p, "CNT-5", assigned_category="archive")  # archive
    db.commit()
    try:
        resp = client.get("/api/v1/issues/tree/counts", params={"project_keys": "CNT"})
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["stack"] == 1
        assert data["active"] == 1
        assert data["initiatives"] == 1
        assert data["archive_target"] == 1
        assert data["archive"] == 1
    finally:
        db.query(Issue).filter(Issue.project_id == p.id).delete()
        db.query(Project).filter(Project.id == p.id).delete()
        db.commit()
```

- [ ] **Step 2: Run — FAIL (404)**

`py -3.10 -m pytest tests/test_issue_tree_lazy_endpoints.py::test_tree_counts_groups_by_tab -v`

- [ ] **Step 3: Implement**

Add to `app/api/endpoints/issue_config.py` (после класса `VerifyRequest`, до endpoint'ов):

```python
class TreeCountsResponse(BaseModel):
    stack: int
    active: int
    initiatives: int
    archive_target: int
    archive: int


ARCHIVE_CATEGORY_CODES = {"archive", "archive_target"}
INITIATIVES_CODE = "initiatives_rfa"


def _filter_query_by_tree_params(query, project_keys, teams, db: Session):
    """Общий фильтр project_keys + teams (как в существующем /tree)."""
    query = query.join(Project, Issue.project_id == Project.id)
    if project_keys:
        scope_keys = [k.strip() for k in project_keys.split(",") if k.strip()]
        if scope_keys:
            query = query.filter(Project.key.in_(scope_keys))
    if teams:
        team_list = [t.strip() for t in teams.split(",") if t.strip()]
        if team_list:
            clauses = []
            for t in team_list:
                t_json = json.dumps(t, ensure_ascii=False)
                clauses.append(Issue.team == t)
                clauses.append(Issue.participating_teams.like(f"%{t_json}%"))
            query = query.filter(or_(*clauses))
    return query


@router.get("/tree/counts", response_model=TreeCountsResponse)
def get_tree_counts(
    project_keys: Optional[str] = None,
    teams: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Счётчики по вкладкам категоризации. Не учитывает pending-правки клиента —
    клиент знает свои pending и сам корректирует UI; при «Сохранить» делает refetch.
    """
    base = _filter_query_by_tree_params(db.query(Issue), project_keys, teams, db)
    rows = base.all()

    # nodeById для walk up
    by_id = {r.id: r for r in rows}
    # Дотащим predков (вне scope) для walk up по inherited категории
    parent_ids_outside = {
        r.parent_id for r in rows
        if r.parent_id and r.parent_id not in by_id
    }
    if parent_ids_outside:
        # Подтянем предков до корня (без team-фильтра — нужны для inherited)
        ancestors = db.query(Issue).filter(Issue.id.in_(parent_ids_outside)).all()
        for a in ancestors:
            by_id[a.id] = a
        # Дотащить выше (parent of parent) — рекурсивно, но обычно 2-3 уровня
        frontier = {a.parent_id for a in ancestors if a.parent_id and a.parent_id not in by_id}
        while frontier:
            batch = db.query(Issue).filter(Issue.id.in_(frontier)).all()
            frontier = set()
            for a in batch:
                if a.id in by_id:
                    continue
                by_id[a.id] = a
                if a.parent_id and a.parent_id not in by_id:
                    frontier.add(a.parent_id)

    def effective(node: Issue) -> Optional[str]:
        if not (node.category_verified or False):
            return None
        if node.assigned_category:
            return node.assigned_category
        cur_id = node.parent_id
        for _ in range(20):
            if not cur_id:
                return None
            parent = by_id.get(cur_id)
            if not parent:
                return None
            if parent.assigned_category:
                return parent.assigned_category
            cur_id = parent.parent_id
        return None

    counts = {"stack": 0, "active": 0, "initiatives": 0, "archive_target": 0, "archive": 0}
    for r in rows:
        eff = effective(r)
        if eff is None:
            counts["stack"] += 1
        elif eff == INITIATIVES_CODE:
            counts["initiatives"] += 1
        elif eff == "archive_target":
            counts["archive_target"] += 1
        elif eff == "archive":
            counts["archive"] += 1
        else:
            counts["active"] += 1
    return TreeCountsResponse(**counts)
```

- [ ] **Step 4: Run — PASS**

`py -3.10 -m pytest tests/test_issue_tree_lazy_endpoints.py::test_tree_counts_groups_by_tab -v`

- [ ] **Step 5: Commit**

```bash
git add app/api/endpoints/issue_config.py tests/test_issue_tree_lazy_endpoints.py
git commit -m "feat(categories): /issues/tree/counts — счётчики по вкладкам"
```

---

## Task 3: Backend — `/issues/tree/roots` endpoint

**Files:**
- Modify: `app/api/endpoints/issue_config.py`
- Test: `tests/test_issue_tree_lazy_endpoints.py` (append)

- [ ] **Step 1: Падающие тесты**

Append to test file:

```python
def test_tree_roots_returns_matching_for_stack_tab(client, db):
    p = _mk_proj(db, "RTS")
    epic = _mk_issue(db, p, "RTS-1", issue_type="Epic", assigned_category="dev")
    child = _mk_issue(db, p, "RTS-2", parent_id=epic.id,
                      assigned_category=None, category_verified=False)
    # одиночка stack
    _mk_issue(db, p, "RTS-3", assigned_category=None, category_verified=False)
    # уже разобран, не должен попасть в stack
    _mk_issue(db, p, "RTS-4", assigned_category="dev")
    db.commit()
    try:
        resp = client.get("/api/v1/issues/tree/roots", params={
            "project_keys": "RTS", "tab": "stack",
        })
        assert resp.status_code == 200, resp.text
        items = resp.json()
        keys = sorted([n["key"] for n in items])
        # Эпик попал в roots, потому что у него внутри есть stack-потомок
        assert "RTS-1" in keys
        assert "RTS-3" in keys
        # has_children + descendant_match_count проставлены
        epic_node = next(n for n in items if n["key"] == "RTS-1")
        assert epic_node["has_children"] is True
        assert epic_node["descendant_match_count"] >= 1
        single = next(n for n in items if n["key"] == "RTS-3")
        assert single["has_children"] is False
    finally:
        db.query(Issue).filter(Issue.project_id == p.id).delete()
        db.query(Project).filter(Project.id == p.id).delete()
        db.commit()


def test_tree_roots_supports_search(client, db):
    p = _mk_proj(db, "SRC")
    _mk_issue(db, p, "SRC-1", summary="оплата заказа", assigned_category=None, category_verified=False)
    _mk_issue(db, p, "SRC-2", summary="отгрузка товара", assigned_category=None, category_verified=False)
    db.commit()
    try:
        resp = client.get("/api/v1/issues/tree/roots", params={
            "project_keys": "SRC", "tab": "stack", "search": "оплат",
        })
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        assert items[0]["key"] == "SRC-1"
    finally:
        db.query(Issue).filter(Issue.project_id == p.id).delete()
        db.query(Project).filter(Project.id == p.id).delete()
        db.commit()
```

- [ ] **Step 2: Run — FAIL**

`py -3.10 -m pytest tests/test_issue_tree_lazy_endpoints.py -v -k roots`

- [ ] **Step 3: Implement**

Append to `app/api/endpoints/issue_config.py`:

```python
class IssueTreeRootNode(BaseModel):
    id: str
    key: str
    summary: str
    issue_type: str
    status: str
    status_category: Optional[str] = None
    project_key: str
    parent_key: Optional[str] = None
    assigned_category: Optional[str] = None
    category: Optional[str] = None
    include_in_analysis: bool = True
    status_changed_at: Optional[str] = None
    goals: Optional[str] = None
    is_context: bool = False
    is_container: bool = False
    category_verified: bool = True
    require_child_verification: bool = False
    has_children: bool = False
    descendant_count: int = 0
    descendant_match_count: int = 0


def _node_matches_tab(effective_code: Optional[str], verified: bool, tab: str) -> bool:
    if not verified:
        return tab == "stack"
    if tab == "stack":
        return effective_code is None
    if tab == "active":
        return (effective_code is not None
                and effective_code not in ARCHIVE_CATEGORY_CODES
                and effective_code != INITIATIVES_CODE)
    if tab == "initiatives":
        return effective_code == INITIATIVES_CODE
    if tab == "archive_target":
        return effective_code == "archive_target"
    if tab == "archive":
        return effective_code == "archive"
    return False


@router.get("/tree/roots", response_model=List[IssueTreeRootNode])
def get_tree_roots(
    project_keys: Optional[str] = None,
    teams: Optional[str] = None,
    tab: str = "stack",
    search: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Корневые узлы вкладки. «Корень» = верхнеуровневая задача (или эпик),
    которая сама матчит вкладку ИЛИ содержит матчащих потомков.

    Поиск (`search`) применяется к key + summary (LIKE %q%). Если поиск
    задан, в корни попадают только узлы, чьё поддерево содержит совпадение,
    с теми же tab-критериями.
    """
    base = _filter_query_by_tree_params(db.query(Issue), project_keys, teams, db)
    rows = base.all()
    matched_ids = {r.id for r in rows}

    # Дотащим предков для walk up + контекст
    by_id: dict[str, Issue] = {r.id: r for r in rows}
    context_ids: set[str] = set()
    frontier = {r.parent_id for r in rows if r.parent_id and r.parent_id not in matched_ids}
    while frontier:
        batch = db.query(Issue).filter(Issue.id.in_(frontier)).all()
        next_f = set()
        for a in batch:
            if a.id in by_id:
                continue
            by_id[a.id] = a
            context_ids.add(a.id)
            if a.parent_id and a.parent_id not in by_id:
                next_f.add(a.parent_id)
        frontier = next_f

    project_key_by_id = {
        p.id: p.key
        for p in db.query(Project)
        .filter(Project.id.in_({r.project_id for r in by_id.values() if r.project_id}))
        .all()
    }

    rules = load_rules(db)

    def effective(node: Issue) -> Optional[str]:
        if not (node.category_verified or False):
            return None
        if node.assigned_category:
            return node.assigned_category
        cur_id = node.parent_id
        for _ in range(20):
            if not cur_id:
                return None
            parent = by_id.get(cur_id)
            if not parent:
                return None
            if parent.assigned_category:
                return parent.assigned_category
            cur_id = parent.parent_id
        return None

    search_lc = (search or "").strip().lower()

    def text_matches(node: Issue) -> bool:
        if not search_lc:
            return True
        return search_lc in (node.key or "").lower() or search_lc in (node.summary or "").lower()

    # Узел "self_matches" если: tab match + (нет поиска ИЛИ text match)
    self_match: dict[str, bool] = {}
    for r in by_id.values():
        self_match[r.id] = (
            _node_matches_tab(effective(r), r.category_verified or False, tab)
            and text_matches(r)
        )

    # children index
    children_by_parent: dict[str, list[Issue]] = {}
    for r in by_id.values():
        if r.parent_id:
            children_by_parent.setdefault(r.parent_id, []).append(r)

    # Подсчёт потомков (всех + матчащих) bottom-up
    desc_total: dict[str, int] = {}
    desc_match: dict[str, int] = {}
    def compute_desc(node_id: str) -> tuple[int, int]:
        if node_id in desc_total:
            return desc_total[node_id], desc_match[node_id]
        t = 0
        m = 0
        for ch in children_by_parent.get(node_id, []):
            t += 1
            if self_match.get(ch.id):
                m += 1
            ct, cm = compute_desc(ch.id)
            t += ct
            m += cm
        desc_total[node_id] = t
        desc_match[node_id] = m
        return t, m

    for r in by_id.values():
        compute_desc(r.id)

    # Включаем в roots: top-level (parent отсутствует или parent не в by_id) +
    # self_match OR descendant_match_count > 0
    roots: list[IssueTreeRootNode] = []
    for r in by_id.values():
        is_top = (not r.parent_id) or (r.parent_id not in by_id)
        if not is_top:
            continue
        if not self_match.get(r.id) and desc_match.get(r.id, 0) == 0:
            continue
        is_container = classify(rules, EvaluationInput(
            project_key=project_key_by_id.get(r.project_id, ""),
            issue_type=r.issue_type,
            has_parent=bool(r.parent_id),
        ))
        roots.append(IssueTreeRootNode(
            id=r.id,
            key=r.key,
            summary=r.summary,
            issue_type=r.issue_type,
            status=r.status,
            status_category=r.status_category,
            project_key=project_key_by_id.get(r.project_id, ""),
            parent_key=by_id[r.parent_id].key if r.parent_id and r.parent_id in by_id else None,
            assigned_category=r.assigned_category,
            category=r.category,
            include_in_analysis=r.include_in_analysis if r.include_in_analysis is not None else True,
            status_changed_at=r.status_changed_at.isoformat() if r.status_changed_at else None,
            goals=r.goals or None,
            is_context=r.id in context_ids,
            is_container=is_container,
            category_verified=r.category_verified if r.category_verified is not None else True,
            require_child_verification=r.require_child_verification if r.require_child_verification is not None else False,
            has_children=bool(children_by_parent.get(r.id)),
            descendant_count=desc_total.get(r.id, 0),
            descendant_match_count=desc_match.get(r.id, 0),
        ))

    roots.sort(key=lambda n: n.key)
    return roots
```

- [ ] **Step 4: Run — PASS**

`py -3.10 -m pytest tests/test_issue_tree_lazy_endpoints.py -v -k roots`

- [ ] **Step 5: Commit**

```bash
git add app/api/endpoints/issue_config.py tests/test_issue_tree_lazy_endpoints.py
git commit -m "feat(categories): /issues/tree/roots — корни вкладки с has_children/descendant_match_count"
```

---

## Task 4: Backend — extend `/issues/{id}/children` with `tab` filter

**Files:**
- Modify: `app/api/endpoints/issue_config.py` — расширить существующий `get_issue_children`
- Test: `tests/test_issue_tree_lazy_endpoints.py` (append)

- [ ] **Step 1: Падающий тест**

```python
def test_children_endpoint_filters_by_tab(client, db):
    p = _mk_proj(db, "CHL")
    epic = _mk_issue(db, p, "CHL-1", issue_type="Epic", assigned_category="dev")
    _mk_issue(db, p, "CHL-2", parent_id=epic.id,
              assigned_category=None, category_verified=False)  # stack
    _mk_issue(db, p, "CHL-3", parent_id=epic.id,
              assigned_category="dev")  # active (через свою dev)
    _mk_issue(db, p, "CHL-4", parent_id=epic.id,
              assigned_category="archive")  # archive
    db.commit()
    try:
        resp_stack = client.get(f"/api/v1/issues/{epic.id}/children", params={"tab": "stack"})
        assert resp_stack.status_code == 200
        keys = sorted([n["key"] for n in resp_stack.json()])
        assert keys == ["CHL-2"]

        resp_archive = client.get(f"/api/v1/issues/{epic.id}/children", params={"tab": "archive"})
        keys = sorted([n["key"] for n in resp_archive.json()])
        assert keys == ["CHL-4"]

        # Без tab — все дети
        resp_all = client.get(f"/api/v1/issues/{epic.id}/children")
        keys = sorted([n["key"] for n in resp_all.json()])
        assert keys == ["CHL-2", "CHL-3", "CHL-4"]
    finally:
        db.query(Issue).filter(Issue.project_id == p.id).delete()
        db.query(Project).filter(Project.id == p.id).delete()
        db.commit()
```

- [ ] **Step 2: Run — FAIL**

`py -3.10 -m pytest tests/test_issue_tree_lazy_endpoints.py -v -k tab`

- [ ] **Step 3: Modify `get_issue_children`**

Найти в `app/api/endpoints/issue_config.py` существующий `get_issue_children` (около строки 562). Расширить:

```python
@router.get("/{parent_id}/children", response_model=List[IssueTreeRootNode])
def get_issue_children(
    parent_id: str,
    tab: Optional[str] = None,
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """Прямые + транзитивные дети, отфильтрованные по вкладке (если задана).

    Возвращает узлы, которые: являются потомками `parent_id` (на любой глубине)
    И сами матчат вкладку. Это позволяет ленивому раскрытию эпика подгрузить
    сразу всех stack-потомков, не раскрывая промежуточные уровни.

    Без `tab` — только прямые дети (обратная совместимость с popover-соседями).
    """
    parent = db.get(Issue, parent_id)
    if not parent:
        raise HTTPException(status_code=404, detail="Задача не найдена")

    if not tab:
        children = (
            db.query(Issue)
            .filter(Issue.parent_id == parent_id)
            .order_by(Issue.key)
            .limit(limit)
            .all()
        )
        project_keys = {
            p.id: p.key
            for p in db.query(Project).filter(Project.id.in_({c.project_id for c in children if c.project_id})).all()
        }
        rules = load_rules(db)
        return [
            IssueTreeRootNode(
                id=ch.id,
                key=ch.key,
                summary=ch.summary,
                issue_type=ch.issue_type,
                status=ch.status,
                status_category=ch.status_category,
                project_key=project_keys.get(ch.project_id, ""),
                parent_key=parent.key,
                assigned_category=ch.assigned_category,
                category=ch.category,
                include_in_analysis=ch.include_in_analysis if ch.include_in_analysis is not None else True,
                status_changed_at=ch.status_changed_at.isoformat() if ch.status_changed_at else None,
                goals=ch.goals or None,
                is_context=False,
                is_container=classify(rules, EvaluationInput(
                    project_key=project_keys.get(ch.project_id, ""),
                    issue_type=ch.issue_type,
                    has_parent=True,
                )),
                category_verified=ch.category_verified if ch.category_verified is not None else True,
                require_child_verification=ch.require_child_verification if ch.require_child_verification is not None else False,
                has_children=db.query(Issue.id).filter(Issue.parent_id == ch.id).first() is not None,
                descendant_count=0,
                descendant_match_count=0,
            )
            for ch in children
        ]

    # С tab: BFS, собираем все поддерево, считаем effective, фильтруем
    subtree: dict[str, Issue] = {}
    frontier = [parent_id]
    while frontier:
        batch = db.query(Issue).filter(Issue.parent_id.in_(frontier)).limit(limit * 5).all()
        next_f = []
        for ch in batch:
            if ch.id in subtree:
                continue
            subtree[ch.id] = ch
            next_f.append(ch.id)
        frontier = next_f

    by_id_full = dict(subtree)
    by_id_full[parent.id] = parent
    # Дотащим предков parent для walk up effective
    cur = parent
    while cur.parent_id and cur.parent_id not in by_id_full:
        anc = db.get(Issue, cur.parent_id)
        if not anc:
            break
        by_id_full[anc.id] = anc
        cur = anc

    def effective(node: Issue) -> Optional[str]:
        if not (node.category_verified or False):
            return None
        if node.assigned_category:
            return node.assigned_category
        cur_id = node.parent_id
        for _ in range(20):
            if not cur_id:
                return None
            par = by_id_full.get(cur_id)
            if not par:
                return None
            if par.assigned_category:
                return par.assigned_category
            cur_id = par.parent_id
        return None

    matched = [
        ch for ch in subtree.values()
        if _node_matches_tab(effective(ch), ch.category_verified or False, tab)
    ]
    matched.sort(key=lambda c: c.key)
    matched = matched[:limit]

    project_keys = {
        p.id: p.key
        for p in db.query(Project).filter(Project.id.in_({c.project_id for c in matched if c.project_id})).all()
    }
    rules = load_rules(db)
    return [
        IssueTreeRootNode(
            id=ch.id,
            key=ch.key,
            summary=ch.summary,
            issue_type=ch.issue_type,
            status=ch.status,
            status_category=ch.status_category,
            project_key=project_keys.get(ch.project_id, ""),
            parent_key=by_id_full[ch.parent_id].key if ch.parent_id in by_id_full else None,
            assigned_category=ch.assigned_category,
            category=ch.category,
            include_in_analysis=ch.include_in_analysis if ch.include_in_analysis is not None else True,
            status_changed_at=ch.status_changed_at.isoformat() if ch.status_changed_at else None,
            goals=ch.goals or None,
            is_context=False,
            is_container=classify(rules, EvaluationInput(
                project_key=project_keys.get(ch.project_id, ""),
                issue_type=ch.issue_type,
                has_parent=bool(ch.parent_id),
            )),
            category_verified=ch.category_verified if ch.category_verified is not None else True,
            require_child_verification=ch.require_child_verification if ch.require_child_verification is not None else False,
            has_children=any(c.parent_id == ch.id for c in subtree.values()),
            descendant_count=0,
            descendant_match_count=0,
        )
        for ch in matched
    ]
```

(Изменение типа `response_model` с `List[IssueChildNode]` на `List[IssueTreeRootNode]` — единая схема узла. Старый `IssueChildNode` в `app/schemas/issue_context.py` остаётся для других callsite'ов.)

- [ ] **Step 4: Run — PASS (3 sub-cases)**

`py -3.10 -m pytest tests/test_issue_tree_lazy_endpoints.py -v -k tab`

- [ ] **Step 5: Commit**

```bash
git add app/api/endpoints/issue_config.py tests/test_issue_tree_lazy_endpoints.py
git commit -m "feat(categories): /issues/{id}/children — фильтр по tab для ленивого раскрытия"
```

---

## Task 5: Backend — `/issues/tree/epic-candidates` endpoint

**Files:**
- Modify: `app/api/endpoints/issue_config.py`
- Test: `tests/test_issue_tree_lazy_endpoints.py` (append)

- [ ] **Step 1: Падающий тест**

```python
def test_epic_candidates_returns_epics_with_assigned_and_children(client, db):
    p = _mk_proj(db, "EPC")
    e1 = _mk_issue(db, p, "EPC-1", issue_type="Epic", assigned_category="dev")
    _mk_issue(db, p, "EPC-2", parent_id=e1.id, assigned_category=None, category_verified=False)
    # Эпик без assigned — НЕ кандидат
    e2 = _mk_issue(db, p, "EPC-3", issue_type="Epic", assigned_category=None)
    _mk_issue(db, p, "EPC-4", parent_id=e2.id)
    # Эпик без детей — НЕ кандидат
    _mk_issue(db, p, "EPC-5", issue_type="Epic", assigned_category="dev")
    db.commit()
    try:
        resp = client.get("/api/v1/issues/tree/epic-candidates", params={"project_keys": "EPC"})
        assert resp.status_code == 200
        items = resp.json()
        keys = sorted([n["key"] for n in items])
        assert keys == ["EPC-1"]
        cand = items[0]
        assert cand["assigned_category"] == "dev"
        assert cand["summary"] == "EPC-1"
    finally:
        db.query(Issue).filter(Issue.project_id == p.id).delete()
        db.query(Project).filter(Project.id == p.id).delete()
        db.commit()
```

- [ ] **Step 2: Run — FAIL**

`py -3.10 -m pytest tests/test_issue_tree_lazy_endpoints.py -v -k epic_candidates`

- [ ] **Step 3: Implement**

Append to `app/api/endpoints/issue_config.py`:

```python
class EpicCandidateSchema(BaseModel):
    id: str
    key: str
    summary: str
    assigned_category: str


@router.get("/tree/epic-candidates", response_model=List[EpicCandidateSchema])
def get_epic_candidates(
    project_keys: Optional[str] = None,
    teams: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Задачи с assigned_category и хотя бы одним ребёнком — кандидаты на каскад
    в bulk-drawer. Фильтр scope/teams тот же, что у tree/roots.
    """
    base = _filter_query_by_tree_params(db.query(Issue), project_keys, teams, db)
    base = base.filter(Issue.assigned_category.isnot(None))
    candidates = base.all()
    # has_children check
    ids_with_kids = {
        cid for (cid,) in db.query(Issue.parent_id)
        .filter(Issue.parent_id.in_({c.id for c in candidates}))
        .distinct().all()
    }
    return [
        EpicCandidateSchema(
            id=c.id, key=c.key, summary=c.summary,
            assigned_category=c.assigned_category,
        )
        for c in candidates if c.id in ids_with_kids
    ]
```

- [ ] **Step 4: Run — PASS**

`py -3.10 -m pytest tests/test_issue_tree_lazy_endpoints.py -v -k epic_candidates`

- [ ] **Step 5: Commit**

```bash
git add app/api/endpoints/issue_config.py tests/test_issue_tree_lazy_endpoints.py
git commit -m "feat(categories): /issues/tree/epic-candidates для cascade-секции drawer'а"
```

---

## Task 6: Frontend — типы + API-обёртки

**Files:**
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/api/issues.ts`

- [ ] **Step 1: Добавить типы**

Append to `frontend/src/types/api.ts`:

```typescript
export type IssueTreeRootNode = {
  id: string;
  key: string;
  summary: string;
  issue_type: string;
  status: string;
  status_category: string | null;
  project_key: string;
  parent_key: string | null;
  assigned_category: string | null;
  category: string | null;
  include_in_analysis: boolean;
  status_changed_at: string | null;
  goals: string | null;
  is_context: boolean;
  is_container: boolean;
  category_verified: boolean;
  require_child_verification: boolean;
  has_children: boolean;
  descendant_count: number;
  descendant_match_count: number;
};

export type IssueTreeCounts = {
  stack: number;
  active: number;
  initiatives: number;
  archive_target: number;
  archive: number;
};

export type EpicCandidateApi = {
  id: string;
  key: string;
  summary: string;
  assigned_category: string;
};
```

- [ ] **Step 2: Добавить API-обёртки**

Append to `frontend/src/api/issues.ts`:

```typescript
import type {
  IssueTreeRootNode,
  IssueTreeCounts,
  EpicCandidateApi,
} from '../types/api';

export const getTreeRoots = (
  params: { project_keys?: string; teams?: string; tab: string; search?: string },
  signal?: AbortSignal,
) => api.get<IssueTreeRootNode[]>('/issues/tree/roots', params as Record<string, string | undefined>, signal);

export const getTreeCounts = (
  params: { project_keys?: string; teams?: string },
  signal?: AbortSignal,
) => api.get<IssueTreeCounts>('/issues/tree/counts', params as Record<string, string | undefined>, signal);

export const getIssueChildrenByTab = (parentId: string, tab: string, limit = 200) =>
  api.get<IssueTreeRootNode[]>(`/issues/${parentId}/children`, { tab, limit: String(limit) });

export const getEpicCandidates = (
  params: { project_keys?: string; teams?: string },
  signal?: AbortSignal,
) => api.get<EpicCandidateApi[]>('/issues/tree/epic-candidates', params as Record<string, string | undefined>, signal);
```

Расширить существующий `import type` (там уже есть `IssueChildNode, IssueContextResponse, IssueTreeNode, BulkFilter...`) — добавить `IssueTreeRootNode, IssueTreeCounts, EpicCandidateApi`.

- [ ] **Step 3: Лента**

`cd frontend && npm run lint 2>&1 | grep -E "types/api|api/issues" || echo "no new errors"`

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/api.ts frontend/src/api/issues.ts
git commit -m "feat(categories): фронт-типы + API-обёртки для ленивых tree-эндпоинтов"
```

---

## Task 7: Frontend — хуки `useIssueLazyTree`

**Files:**
- Create: `frontend/src/hooks/useIssueLazyTree.ts`

- [ ] **Step 1: Создать файл**

```typescript
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getTreeRoots,
  getTreeCounts,
  getIssueChildrenByTab,
  getEpicCandidates,
} from '../api/issues';

type RootsParams = {
  project_keys?: string;
  teams?: string;
  tab: 'stack' | 'active' | 'initiatives' | 'archive_target' | 'archive';
  search?: string;
};

export function useIssueRoots(params: RootsParams) {
  return useQuery({
    queryKey: ['issues', 'tree', 'roots', params],
    queryFn: ({ signal }) => getTreeRoots(params, signal),
    enabled: !!(params.teams || params.project_keys),
    retry: false,
    staleTime: 30_000,
  });
}

type CountsParams = { project_keys?: string; teams?: string };

export function useIssueTreeCounts(params: CountsParams) {
  return useQuery({
    queryKey: ['issues', 'tree', 'counts', params],
    queryFn: ({ signal }) => getTreeCounts(params, signal),
    enabled: !!(params.teams || params.project_keys),
    retry: false,
    staleTime: 30_000,
  });
}

export function useEpicCandidates(params: CountsParams) {
  return useQuery({
    queryKey: ['issues', 'tree', 'epic-candidates', params],
    queryFn: ({ signal }) => getEpicCandidates(params, signal),
    enabled: !!(params.teams || params.project_keys),
    retry: false,
    staleTime: 30_000,
  });
}

export function useLoadChildrenMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ parentId, tab }: { parentId: string; tab: string }) =>
      getIssueChildrenByTab(parentId, tab),
    onSuccess: (_data, vars) => {
      // ничего глобально не инвалидируем — потомки кладутся в локальный state страницы
      void vars;
      void qc;
    },
  });
}
```

- [ ] **Step 2: Lint**

`cd frontend && npm run lint 2>&1 | grep useIssueLazyTree || echo "ok"`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/hooks/useIssueLazyTree.ts
git commit -m "feat(categories): хуки useIssueRoots/Counts/EpicCandidates/LoadChildren"
```

---

## Task 8: Frontend — переписать `CategoriesEditorPage` под ленивое дерево

**Files:**
- Modify: `frontend/src/pages/CategoriesEditorPage.tsx`

Это самая большая задача. Она замещает 5 локальных walks (`buildTabData`, `descendantCounts`, `nodeById`, `epicCandidates`, `countTriage`) серверными хуками и добавляет lazy expand.

- [ ] **Step 1: Заменить импорты + state**

В начале файла:

```typescript
// БЫЛО: import { useIssueTree, useSetIssueInclude, useBatchSetCategory, useVerifyIssue } from '../hooks/useIssueTree';
// СТАЛО:
import {
  useIssueRoots,
  useIssueTreeCounts,
  useLoadChildrenMutation,
} from '../hooks/useIssueLazyTree';
import { useSetIssueInclude, useBatchSetCategory, useVerifyIssue } from '../hooks/useIssueTree';
import type { IssueTreeRootNode } from '../types/api';
```

`IssueTreeNode` (вложенный) больше не используется страницей напрямую — заменяем на `IssueTreeRootNode` (плоский с has_children/descendant_count).

`TreeNodeWithChildren` type — оставляем, но определяем через RootNode:

```typescript
type TreeNodeWithChildren = IssueTreeRootNode & {
  children?: TreeNodeWithChildren[];
  __depth?: number;
};
// УБРАТЬ поле __inheritedAssigned — теперь сервер сам считает effective при tab filter
```

- [ ] **Step 2: Заменить fetch на rootsQuery + countsQuery**

```typescript
const rootsQuery = useIssueRoots({
  project_keys: scopeKeys || undefined,
  teams: selectedTeams.length > 0 ? selectedTeams.join(',') : undefined,
  tab: innerTab,
  search: normalizedSearch || undefined,
});
const countsQuery = useIssueTreeCounts({
  project_keys: scopeKeys || undefined,
  teams: selectedTeams.length > 0 ? selectedTeams.join(',') : undefined,
});
```

(`innerTab` уже есть в state.)

- [ ] **Step 3: Lazy expand state + handler**

```typescript
const [loadedChildren, setLoadedChildren] = useState<Map<string, IssueTreeRootNode[]>>(new Map());
const loadChildrenMut = useLoadChildrenMutation();

const onExpand = useCallback(async (expanded: boolean, record: TreeNodeWithChildren) => {
  if (!expanded) return;  // схлопывание ничего не грузит
  if (loadedChildren.has(record.id)) return;  // уже загружены
  if (!record.has_children) return;
  const children = await loadChildrenMut.mutateAsync({ parentId: record.id, tab: innerTab });
  setLoadedChildren(prev => {
    const next = new Map(prev);
    next.set(record.id, children);
    return next;
  });
}, [loadedChildren, loadChildrenMut, innerTab]);
```

Сброс loadedChildren при смене вкладки или фильтра команды:

```typescript
useEffect(() => {
  setLoadedChildren(new Map());
  setExpandedRowKeys([]);
}, [innerTab, selectedTeams, scopeKeys, normalizedSearch]);
```

- [ ] **Step 4: Построить `displayData` из roots + loadedChildren**

Заменяет `stackData`/`activeData`/.../`displayData`/`buildTabData`. Все 5 memos удаляются.

```typescript
const displayData = useMemo<TreeNodeWithChildren[]>(() => {
  const attachChildren = (node: IssueTreeRootNode, depth: number): TreeNodeWithChildren => {
    const kids = loadedChildren.get(node.id);
    return {
      ...node,
      __depth: depth,
      children: kids?.map(k => attachChildren(k, depth + 1)),
    };
  };
  return (rootsQuery.data ?? []).map(r => attachChildren(r, 0));
}, [rootsQuery.data, loadedChildren]);
```

- [ ] **Step 5: Заменить tab-счётчики на counts из сервера**

Удалить `stackCount, activeCount, ... countTriage` и `queueItems` пересчёт через них. Перестроить:

```typescript
const counts = countsQuery.data ?? { stack: 0, active: 0, initiatives: 0, archive_target: 0, archive: 0 };
const queueItems = useMemo(() => QUEUE_ORDER.map(key => ({
  key,
  count: counts[key],
  ...QUEUE_META[key],
})), [counts]);
```

(`stackCount` — теперь `counts.stack`. Заголовочный «N ждут разбора» использует `counts.stack`.)

- [ ] **Step 6: Удалить `nodeById` + `descendantCounts` + `epicCandidates`**

- `nodeById` использовался только в `setPendingCategory` cascade — будет работать с loaded children (см. шаг 7).
- `descendantCounts` — теперь поле `descendant_count` в каждом узле. В колонке «Название» меняем `descendantCounts.get(record.id) ?? 0` → `record.descendant_count`.
- `epicCandidates` — удаляем; bulk drawer получает их из своего собственного хука (Task 10).

- [ ] **Step 7: Адаптировать `setPendingCategory` cascade**

Старая логика обходила `nodeById.get(issueId)` и спускалась по поддереву. Теперь нет полного дерева — есть только то, что загружено. Меняем поведение:

```typescript
const setPendingCategory = useCallback((issueId: string, code: string | null) => {
  setPendingCats(prev => {
    const next = new Map(prev);
    next.set(issueId, code);
    cascadedIdsRef.current.delete(issueId);

    if (innerTab !== 'stack') return next;

    // Каскад только на ВИДИМЫЕ загруженные потомки (то, что в loadedChildren).
    // PM, который не раскрыл эпик, не ждёт каскада на скрытое поддерево.
    const cascaded = cascadedIdsRef.current;
    const visit = (parentId: string) => {
      const kids = loadedChildren.get(parentId);
      if (!kids) return;
      for (const ch of kids) {
        if (ch.issue_type === 'group') { visit(ch.id); continue; }
        if (ch.is_context) continue;
        if (ch.assigned_category) continue;
        const hasPending = next.has(ch.id);
        const isCascaded = cascaded.has(ch.id);
        if (hasPending && !isCascaded) continue;
        if (code === null) {
          if (hasPending && isCascaded) {
            next.delete(ch.id);
            cascaded.delete(ch.id);
          }
        } else {
          next.set(ch.id, code);
          cascaded.add(ch.id);
        }
        visit(ch.id);
      }
    };
    visit(issueId);
    return next;
  });
}, [innerTab, loadedChildren]);
```

- [ ] **Step 8: Заменить `expandAll` + `collapseAll`**

```typescript
const expandAll = useCallback(() => {
  message.info('Раскрыть всё недоступно для больших деревьев. Раскрывайте интересующие эпики по клику.');
}, [message]);
const collapseAll = useCallback(() => {
  setExpandedRowKeys([]);
  setLoadedChildren(new Map());
}, []);
```

(`message` — нужно добавить `App.useApp()` сверху, если не было.)

- [ ] **Step 9: Search auto-expand отключаем**

Удалить useEffect `if (!normalizedSearch) return; ... walk(displayData); setExpandedRowKeys(...)` — серверный поиск уже сузил roots, дополнительно ничего не раскрываем.

- [ ] **Step 10: Передать `onExpand` в Table**

```typescript
const tableExpandable = useMemo(
  () => ({
    expandedRowKeys,
    onExpandedRowsChange: setExpandedRowKeys,
    onExpand,
    expandRowByClick: true,
  }),
  [expandedRowKeys, onExpand],
);
```

- [ ] **Step 11: Loading state**

В Table props: `loading={rootsQuery.isFetching || loadChildrenMut.isPending}`.

- [ ] **Step 12: Обновить инвалидации после mutate**

`toggleInclude` и `handleVerify` сейчас патчат локальный кэш `treeQueryKey = ['issues', 'tree', issueTreeParams]`. Этого кэша больше нет. Меняем на инвалидацию `['issues', 'tree']`:

```typescript
// в toggleInclude / handleVerify / savePending — везде где qc.setQueryData(treeQueryKey, ...) или issueTree.refetch():
qc.invalidateQueries({ queryKey: ['issues', 'tree'] });
```

(Все запросы под этим префиксом — `roots`, `counts`, `epic-candidates` — инвалидируются. После сохранения дерево перегрузится.)

- [ ] **Step 13: Lint + build**

```bash
cd frontend && npm run lint 2>&1 | grep -E "CategoriesEditorPage" | head -10
cd frontend && npm run build 2>&1 | tail -5
```

Build должен пройти. Lint может выдать unused-vars на удалённых импортах — почистить.

- [ ] **Step 14: Commit**

```bash
git add frontend/src/pages/CategoriesEditorPage.tsx
git commit -m "feat(categories): page rewritten для ленивого дерева"
```

---

## Task 9: Frontend — BulkCascadeInheritSection получает кандидатов из своего хука

**Files:**
- Modify: `frontend/src/components/categories/sections/BulkCascadeInheritSection.tsx`
- Modify: `frontend/src/components/categories/BulkTriageDrawer.tsx`
- Modify: `frontend/src/pages/CategoriesEditorPage.tsx`

- [ ] **Step 1: Обновить `BulkCascadeInheritSection.tsx`**

Заменить пропс `candidates` на собственный fetch. Принять `selectedTeams` + `scopeProjectKeys`:

```typescript
import { useEpicCandidates } from '../../../hooks/useIssueLazyTree';
// ...
type Props = {
  selectedTeams: string[];
  scopeProjectKeys: string[];
  onApplied: () => void;
};

export default function BulkCascadeInheritSection({ selectedTeams, scopeProjectKeys, onApplied }: Props) {
  const candidatesQuery = useEpicCandidates({
    project_keys: scopeProjectKeys.length > 0 ? scopeProjectKeys.join(',') : undefined,
    teams: selectedTeams.length > 0 ? selectedTeams.join(',') : undefined,
  });
  const candidates = candidatesQuery.data ?? [];
  // ... остальная логика без изменений (Transfer, modal, mutateAsync)
}
```

(`EpicCandidate` type больше не экспортируется — секция использует `EpicCandidateApi` из `types/api`.)

- [ ] **Step 2: Убрать prop `epicCandidates` из Drawer**

`BulkTriageDrawer.tsx`:
- Удалить `epicCandidates: EpicCandidate[]` из Props и из destructure
- Удалить `import ... { type EpicCandidate }`
- Передать `selectedTeams + scopeProjectKeys + onApplied` в `BulkCascadeInheritSection`

- [ ] **Step 3: Убрать передачу из Page**

`CategoriesEditorPage.tsx`:
- Удалить prop `epicCandidates={epicCandidates}` из вызова `<BulkTriageDrawer />`
- `epicCandidates` memo уже удалён в Task 8 — проверить

- [ ] **Step 4: Build + lint**

`cd frontend && npm run build 2>&1 | tail -3`

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/categories/sections/BulkCascadeInheritSection.tsx \
        frontend/src/components/categories/BulkTriageDrawer.tsx \
        frontend/src/pages/CategoriesEditorPage.tsx
git commit -m "feat(categories): cascade-секция тянет кандидатов из useEpicCandidates"
```

---

## Task 10: Финальная проверка + docs + push

- [ ] **Step 1: Backend full suite**

`py -3.10 -m pytest tests/ -x 2>&1 | tail -10`

Expected: All PASS (включая 4 новых теста tree/lazy).

- [ ] **Step 2: Frontend lint + build**

`cd frontend && npm run lint && npm run build`

- [ ] **Step 3: Browser smoke**

Сценарии вручную:
1. Залогиниться, выбрать команду 1С (или другую с >2k задач).
2. Открыть `/categories` — заголовок и счётчики появляются <1с.
3. Кликнуть «Стек» → roots ≤200 узлов рендерятся мгновенно.
4. Раскрыть один эпик — дети тянутся отдельным запросом, появляются.
5. Поиск «оплат» — server-side фильтр, roots сужаются.
6. Назначить категорию эпику → Сохранить → roots обновляются.
7. Открыть «Массовые операции» → секция «Каскад от эпика» — кандидаты тянутся отдельным запросом (Transfer заполнен).

- [ ] **Step 4: Обновить `frontend/CLAUDE.md`**

Раздел `## CategoriesEditorPage (/categories)` — заменить старое описание fetch на:

```
**Ленивая загрузка** через `useIssueRoots/Counts/EpicCandidates/LoadChildren` ([`hooks/useIssueLazyTree.ts`]). Сервер отдаёт только корни вкладки (с `has_children`/`descendant_count`/`descendant_match_count`); потомки тянутся по `onExpand` → endpoint `/issues/{id}/children?tab=...`. Старый full-tree endpoint `/issues/tree` страница не дёргает (но он остаётся для других модулей). Счётчики вкладок — отдельный запрос `/issues/tree/counts`. Поиск — server-side debounced. «Развернуть всё» отключено.
```

- [ ] **Step 5: Обновить `docs/help/categories.md`**

Добавить в конец секции про скорость:

```
**Большие команды.** Когда в команде >1000 задач, дерево раскрывается лениво — сначала видны только корневые задачи и эпики. Чтобы увидеть детей внутри эпика, кликните на стрелочку — потомки подтянутся отдельно. Это сделано чтобы страница открывалась за секунду даже при 6000+ задач.
```

- [ ] **Step 6: Commit + push**

```bash
git add docs/help/categories.md frontend/CLAUDE.md
git commit -m "docs: ленивая загрузка дерева на /categories"
git push origin main
```

---

## Self-Review Notes

- Backend: 4 новых endpoint'а + helper в category_resolver. Все покрыты pytest с реальной БД и cleanup. Полная suite должна давать >1090 PASS.
- Старый `/issues/tree` endpoint НЕ удалён — используется в `useIssueTree.ts` для других страниц/функций; миграцию делаем отдельным шагом если нужно.
- `setPendingCategory` cascade сужен до загруженных потомков. Document'нут в коде комментарием. PM, который не раскрыл эпик, не ждёт каскада на скрытое поддерево — это компромисс ленивого подхода (раньше был полный обход дерева).
- «Развернуть всё» — UI отключён с уведомлением. Не пытаемся ленивoly раскрыть всё (это породит 1000+ запросов).
- Cache invalidation: всё под префиксом `['issues', 'tree']` — `roots`, `counts`, `epic-candidates`. Одна инвалидация после mutate перетягивает всё нужное.
- `expandedRowKeys` сбрасывается при смене вкладки/команды/поиска — иначе AntD пытается раскрыть узлы, которых нет в новых roots.
- Bulk drawer epic candidates — отдельный кэш, инвалидируется вместе с tree после bulk apply.
- Поиск debounced на 300ms — кнопка Input.Search уже это делает через onSearch; продолжаем slать только при изменении `searchQuery`.

Этап 3 (virtual table) будет отдельным планом после shipping этого. Зависит от того, помог ли lazy на реальных данных PM.
