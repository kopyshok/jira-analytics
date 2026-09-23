"""Несколько полей оценки на роль и спорные оценки — чистая логика."""
import json

from app.services.plan_sources import (
    MANUAL_SOURCE,
    SUM_SOURCE,
    Candidate,
    FieldSpec,
    build_candidates,
    candidates_from_json,
    candidates_to_json,
    disputes_for,
    fingerprint,
    parse_field_setting,
    resolve_role,
)

DEV = json.dumps([
    {"field_id": "customfield_12432", "kind": "alt", "name": "Разработка (ч)"},
    {"field_id": "customfield_14648", "kind": "alt", "name": "Оценка 1С (ч)"},
    {"field_id": "customfield_12888", "kind": "sum", "name": "Оценка Back"},
    {"field_id": "customfield_12889", "kind": "sum", "name": "Оценка Front"},
], ensure_ascii=False)


def _cands(setting: str, values: dict) -> tuple:
    return build_candidates(parse_field_setting(setting), values)


class TestParseFieldSetting:
    def test_empty(self):
        assert parse_field_setting(None) == ()
        assert parse_field_setting("") == ()
        assert parse_field_setting("   ") == ()

    def test_legacy_plain_string_is_one_alt(self):
        assert parse_field_setting("customfield_12431") == (
            FieldSpec(field_id="customfield_12431", kind="alt", name=None),
        )

    def test_json_list_keeps_order_kind_name(self):
        specs = parse_field_setting(DEV)
        assert [s.field_id for s in specs] == [
            "customfield_12432", "customfield_14648", "customfield_12888", "customfield_12889",
        ]
        assert [s.kind for s in specs] == ["alt", "alt", "sum", "sum"]
        assert specs[1].name == "Оценка 1С (ч)"

    def test_broken_json_gives_nothing(self):
        assert parse_field_setting("[{") == ()

    def test_unknown_kind_is_alt_and_duplicates_dropped(self):
        raw = json.dumps([
            {"field_id": "cf_1", "kind": "weird"},
            {"field_id": "cf_1", "kind": "sum"},
            {"field_id": ""},
        ])
        assert parse_field_setting(raw) == (FieldSpec("cf_1", "alt", None),)


class TestResolveRole:
    def test_no_candidates(self):
        res = resolve_role((), None)
        assert res.value is None and res.disputed is False

    def test_one_field(self):
        cands = _cands("customfield_12431", {"customfield_12431": 40.0})
        res = resolve_role(cands, None)
        assert res.value == 40.0
        assert res.disputed is False

    def test_empty_field_is_not_a_candidate(self):
        cands = _cands(DEV, {"customfield_12432": 100.0, "customfield_14648": None})
        assert [c.source for c in cands] == ["customfield_12432"]
        assert resolve_role(cands, None).disputed is False

    def test_equal_alts_no_dispute(self):
        cands = _cands(DEV, {"customfield_12432": 100.0, "customfield_14648": 100.0})
        res = resolve_role(cands, None)
        assert res.value == 100.0
        assert res.disputed is False

    def test_different_alts_dispute_default_first(self):
        cands = _cands(DEV, {"customfield_12432": 100.0, "customfield_14648": 120.0})
        res = resolve_role(cands, None)
        assert res.disputed is True
        assert res.value == 100.0

    def test_sum_fields_summed_as_one_candidate_at_first_sum_position(self):
        raw = json.dumps([
            {"field_id": "cf_back", "kind": "sum", "name": "Оценка Back"},
            {"field_id": "cf_main", "kind": "alt", "name": "Разработка (ч)"},
            {"field_id": "cf_front", "kind": "sum", "name": "Оценка Front"},
        ], ensure_ascii=False)
        cands = _cands(raw, {"cf_back": 30.0, "cf_main": 80.0, "cf_front": 50.0})
        assert cands == (
            Candidate(SUM_SOURCE, "Оценка Back + Оценка Front", 80.0),
            Candidate("cf_main", "Разработка (ч)", 80.0),
        )
        res = resolve_role(cands, None)
        assert res.disputed is False  # 30 + 50 == 80
        assert res.value == 80.0

    def test_partial_sum_uses_filled_parts_only(self):
        cands = _cands(DEV, {"customfield_12888": 30.0})
        assert cands == (Candidate(SUM_SOURCE, "Оценка Back", 30.0),)

    def test_sum_vs_alt_dispute(self):
        cands = _cands(DEV, {
            "customfield_12432": 100.0, "customfield_12888": 30.0, "customfield_12889": 50.0,
        })
        res = resolve_role(cands, None)
        assert res.disputed is True
        assert res.value == 100.0
        assert [c.source for c in cands] == ["customfield_12432", SUM_SOURCE]

    def test_choice_valid_until_fingerprint_changes(self):
        before = _cands(DEV, {"customfield_12432": 100.0, "customfield_14648": 120.0})
        choice = {"source": "customfield_14648", "fingerprint": fingerprint(before)}
        res = resolve_role(before, choice)
        assert res.value == 120.0
        assert res.disputed is False

        after = _cands(DEV, {"customfield_12432": 100.0, "customfield_14648": 130.0})
        res2 = resolve_role(after, choice)
        assert res2.value == 100.0
        assert res2.disputed is True

    def test_manual_choice_resolves_only_with_manual_value(self):
        cands = _cands(DEV, {"customfield_12432": 100.0, "customfield_14648": 120.0})
        choice = {"source": MANUAL_SOURCE, "fingerprint": fingerprint(cands)}
        assert resolve_role(cands, choice, has_manual=True).disputed is False
        assert resolve_role(cands, choice, has_manual=True).value == 100.0
        assert resolve_role(cands, choice, has_manual=False).disputed is True

    def test_float_noise_is_not_a_dispute(self):
        cands = (Candidate("a", "A", 0.1 + 0.2), Candidate("b", "B", 0.3))
        assert resolve_role(cands, None).disputed is False


class TestZeroIsNotFilled:
    """Ноль — «поле не заполнено», если у роли есть ненулевое значение."""

    def test_zero_vs_value_takes_value_without_dispute(self):
        cands = _cands(DEV, {"customfield_12432": 0, "customfield_14648": 56.0})
        assert cands == (Candidate("customfield_14648", "Оценка 1С (ч)", 56.0),)
        res = resolve_role(cands, None)
        assert res.value == 56.0
        assert res.disputed is False

    def test_all_zero_gives_zero_without_dispute(self):
        cands = _cands(DEV, {"customfield_12432": 0, "customfield_14648": 0.0})
        res = resolve_role(cands, None)
        assert res.value == 0.0
        assert res.disputed is False

    def test_zero_sum_part_left_out_of_label(self):
        cands = _cands(DEV, {"customfield_12888": 30.0, "customfield_12889": 0})
        assert cands == (Candidate(SUM_SOURCE, "Оценка Back", 30.0),)

    def test_zero_sum_vs_alt_is_not_a_dispute(self):
        cands = _cands(DEV, {
            "customfield_12432": 100.0, "customfield_12888": 0, "customfield_12889": 0,
        })
        assert cands == (Candidate("customfield_12432", "Разработка (ч)", 100.0),)
        assert resolve_role(cands, None).disputed is False


class TestStorage:
    def test_json_roundtrip(self):
        cands = _cands(DEV, {"customfield_12432": 100.0, "customfield_12888": 30.0})
        assert candidates_from_json(candidates_to_json(cands)) == cands

    def test_from_json_tolerates_garbage(self):
        assert candidates_from_json(None) == ()
        assert candidates_from_json([{"source": "x"}, "junk", {"source": "y", "label": "Y", "value": 5}]) == (
            Candidate("y", "Y", 5.0),
        )

    def test_disputes_for(self):
        disputed = _cands(DEV, {"customfield_12432": 100.0, "customfield_14648": 120.0})
        calm = _cands("cf_qa", {"cf_qa": 10.0})
        sources = {"dev": candidates_to_json(disputed), "qa": candidates_to_json(calm)}
        assert disputes_for(sources, None, set()) == {"dev": disputed}
        choice = {"dev": {"source": "customfield_14648", "fingerprint": fingerprint(disputed)}}
        assert disputes_for(sources, choice, set()) == {}
        assert disputes_for(None, None, set()) == {}
