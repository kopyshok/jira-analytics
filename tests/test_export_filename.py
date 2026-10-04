"""Имя файла выгрузки сценария = название сценария."""

import pytest

from app.api.endpoints.exports import scenario_file_name


@pytest.mark.parametrize(
    "name,ext,expected",
    [
        ("План Q4", "xlsx", "План Q4.xlsx"),
        ('a\\b/c:d*e?f"g<h>i|j', "xlsx", "a_b_c_d_e_f_g_h_i_j.xlsx"),
        ("  план  ", "xlsx", "план.xlsx"),
        ("план...", "xlsx", "план.xlsx"),
        ("тест\x00\x1fтест", "pptx", "тест__тест.pptx"),
        ("", "xlsx", "scenario.xlsx"),
        (None, "pptx", "scenario.pptx"),
        ("   ...  ", "xlsx", "scenario.xlsx"),
    ],
)
def test_scenario_file_name(name, ext, expected):
    assert scenario_file_name(name, ext) == expected


def test_scenario_file_name_length_limit():
    result = scenario_file_name("я" * 300, "xlsx")
    assert result == "я" * 150 + ".xlsx"


def test_scenario_file_name_trims_after_cut():
    # после обрезки до 150 на конце оказывается пробел — он не должен остаться
    result = scenario_file_name("а" * 149 + " б", "xlsx")
    assert result == "а" * 149 + ".xlsx"
