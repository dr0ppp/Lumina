from decimal import Decimal

import pytest

from lumina.errors import LuminaError
from lumina.parser import Adjustment, parse_instructions


def dictionaries(text):
    return [operation.to_dict() for operation in parse_instructions(text)]


def test_project_spec_example_keeps_relative_intent():
    assert dictionaries("曝光+0.3，高光降低40，阴影提高30") == [
        {"parameter": "Exposure", "operation": "adjust", "value": .3},
        {"parameter": "Highlights", "operation": "adjust", "value": -40},
        {"parameter": "Shadows", "operation": "adjust", "value": 30},
    ]


@pytest.mark.parametrize("text", [
    "曝光设为+0.3", "曝光设置为0.30 EV", "曝光调整到.3", "Exposure=0.3",
    "exposure: +0.3", "EXPOSURE set to 0.3 ev", "Exposure set 0.3",
    "曝光：＋０．３０ＥＶ。",
])
def test_explicit_assignment(text):
    assert dictionaries(text) == [{"parameter": "Exposure", "operation": "set", "value": .3}]


@pytest.mark.parametrize("text,value", [
    ("曝光降低0.3", "-0.3"), ("曝光-0.3", "-0.3"), ("曝光 − 0.30 EV", "-0.3"),
    ("曝光-=0.3", "-0.3"), ("Exposure decrease by .3", "-0.3"),
    ("曝光增加0.3", "0.3"), ("曝光 + 0.3", "0.3"), ("曝光+=.3EV", "0.3"),
    ("Exposure increase by 0.3", "0.3"), ("曝光+8", "8"),
])
def test_relative_forms(text, value):
    operation, = parse_instructions(text)
    assert operation.operation == "adjust"
    assert operation.value == Decimal(value)


def test_all_parameters_longest_names_and_units():
    operations = dictionaries(
        "曝光设为-0.5; 对比度+10\n高光-20,阴影+30,白色色阶=5,黑色色阶=-5;"
        "色温设为5200K；色调设为20，自然饱和度+15，饱和度-10"
    )
    assert len(operations) == 10
    assert operations[-2]["parameter"] == "Vibrance"
    assert operations[-1]["parameter"] == "Saturation"
    assert operations[6] == {"parameter": "Temperature", "operation": "set", "value": 5200}


@pytest.mark.parametrize("text", [
    "", "  ", ";,\n", "曝光 0.3", "曝光+", "曝光增加", "曝光降低-0.3",
    "曝光增加+0.3", "曝光设为NaN", "曝光设为Infinity", "曝光设为1e2",
    "高光=0.5", "曝光+0.333", "曝光设为5.01", "曝光+10.01", "高光增加201",
    "色温设为1999K", "色温设为50001K", "色调设为151", "饱和度+10%",
    "曝光+0.3K", "色温+100EV", "曝光+0.3。高光-20", "曝光+0.3让画面电影感",
    "高光降低40阴影提高30", "曝光0.3", "电影感", "压高光", "温度设为5000",
    "Exposure=0.3; drop table", "Exposure++0.3", "Exposure set to - 0.3",
])
def test_invalid_or_ambiguous_input_is_rejected_whole(text):
    with pytest.raises(LuminaError):
        parse_instructions(text)


@pytest.mark.parametrize("text", ["曝光+0.3，曝光+0.2", "曝光=0.3; Exposure=0.3"])
def test_duplicate_parameter_rejected_across_aliases(text):
    with pytest.raises(LuminaError, match="重复"):
        parse_instructions(text)


def test_failure_identifies_clause_without_returning_partial_results():
    with pytest.raises(LuminaError, match="第 2 项"):
        parse_instructions("曝光+0.3,随便美化一下")


def test_input_limits():
    with pytest.raises(LuminaError, match="4096"):
        parse_instructions("曝" * 4097)
    with pytest.raises(LuminaError, match="最多"):
        parse_instructions(",".join(["曝光+0.1"] * 11))


def test_model_validates_programmatic_input_and_is_immutable():
    operation = Adjustment("Exposure", "adjust", ".30")
    assert operation.value == Decimal("0.30")
    with pytest.raises(AttributeError):
        operation.parameter = "Contrast"
    for args in [("Mystery", "set", 1), ("Exposure", "guess", 1), ("Tint", "set", True)]:
        with pytest.raises(LuminaError):
            Adjustment(*args)
