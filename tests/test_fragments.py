"""残页拼合规则测试。

直接运行：python tests/test_fragments.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.fragments import (  # noqa: E402
    STATUS_ASSEMBLED,
    STATUS_CONTAINED,
    STATUS_DUPLICATE,
    assemble_fragments,
)


def F(**pairs):
    """name=text 简写为 fragments 列表。"""
    return [{"name": k, "text": v} for k, v in pairs.items()]


def statuses(res):
    return [f["status"] for f in res["fragments"]]


def order_names(res):
    return [step["name"] for step in res["order"]]


def order_indices(res):
    return [step["index"] for step in res["order"]]


def spans(res):
    return {f["name"]: f["span"] for f in res["fragments"]}


def test_chain_overlap():
    # 最长后缀—前缀重叠逐对拼接：ABCD + CDEF(2) + EFGH(2) = ABCDEFGH
    frags = F(甲="ABCD", 乙="CDEF", 丙="EFGH", 丁="CD", 戊="ABCD")
    res = assemble_fragments(frags)
    assert res["text"] == "ABCDEFGH"
    assert res["length"] == 8
    assert res["total_overlap"] == 4
    assert res["participant_count"] == 3
    assert order_names(res) == ["甲", "乙", "丙"]
    assert [step["overlap"] for step in res["order"]] == [0, 2, 2]
    assert statuses(res) == [
        STATUS_ASSEMBLED,
        STATUS_ASSEMBLED,
        STATUS_ASSEMBLED,
        STATUS_CONTAINED,   # 「CD」全文在更长页中
        STATUS_DUPLICATE,   # 与甲同文且录入更晚
    ]
    # 每张残页都在全文中给出最早出现的半开区间
    assert spans(res) == {
        "甲": [0, 4],
        "乙": [2, 6],
        "丙": [4, 8],
        "丁": [2, 4],
        "戊": [0, 4],
    }
    by_name = {x["name"]: x["text"] for x in frags}
    for f in res["fragments"]:
        assert res["text"][f["span"][0]:f["span"][1]] == by_name[f["name"]]


def test_reverse_chain_chosen_by_overlap():
    # 两条成链顺序均得 8 码点（重叠相同），取全文字典序更小的 ABCDEFAB
    res = assemble_fragments(F(甲="EFAB", 乙="ABCD", 丙="CDEF"))
    assert res["text"] == "ABCDEFAB"
    assert order_names(res) == ["乙", "丙", "甲"]
    assert [step["overlap"] for step in res["order"]] == [0, 2, 2]
    assert res["length"] == 8


def test_zero_overlap_lexicographic():
    # 无任何重叠时所有排列等长（3 码点），取全文字典序最小「abc」
    res = assemble_fragments(F(X="b", Y="a", Z="c"))
    assert res["text"] == "abc"
    assert res["length"] == 3
    assert res["total_overlap"] == 0
    assert order_indices(res) == [2, 1, 3]
    assert [step["overlap"] for step in res["order"]] == [0, 0, 0]


def test_lex_tie_between_two_superstrings():
    # 三页「abbx／ax／xxb」每条排列的最优合并均为 8 码点，但全文各异：
    #   abbx→ax→xxb = abbxaxxb
    #   abbx→xxb→ax = abbxxbax
    #   ax→abbx→xxb = axabbxxb
    #   ax→xxb→abbx = axxbabbx
    # 取全文字典序最小者 abbxaxxb（录入序号 1,2,3）。
    res = assemble_fragments(F(p1="abbx", p2="ax", p3="xxb"))
    assert res["text"] == "abbxaxxb"
    assert res["length"] == 8
    assert order_indices(res) == [1, 2, 3]


def test_index_sequence_tie():
    # 两张等长同构页从任一顺序拼接都得到同一全文「abc」时，
    # 取参与拼接的录入序号序列最小者。
    res = assemble_fragments(F(甲="ab", 乙="bc"))
    assert res["text"] == "abc"
    assert order_indices(res) == [1, 2]

    res = assemble_fragments(F(甲="bc", 乙="ab"))
    assert res["text"] == "abc"
    assert order_indices(res) == [2, 1]


def test_contained_page_located_but_not_assembled():
    res = assemble_fragments(F(长="abcde", 短="abc", 他="ef"))
    assert statuses(res) == [STATUS_ASSEMBLED, STATUS_CONTAINED, STATUS_ASSEMBLED]
    assert res["participant_count"] == 2
    assert res["text"] == "abcdef"
    assert order_names(res) == ["长", "他"]
    # 被包含页仍定位最早出现区间
    assert spans(res)["短"] == [0, 3]
    assert spans(res)["长"] == [0, 5]
    assert spans(res)["他"] == [4, 6]


def test_duplicate_keeps_earliest():
    res = assemble_fragments(F(甲="abc", 乙="abc", 丙="bcd"))
    assert statuses(res) == [STATUS_ASSEMBLED, STATUS_DUPLICATE, STATUS_ASSEMBLED]
    assert res["participant_count"] == 2
    assert order_indices(res) == [1, 3]
    assert res["text"] == "abcd"
    assert [step["overlap"] for step in res["order"]] == [0, 2]
    # 同文重复页仍定位（与最早页同一区间）
    assert spans(res)["甲"] == [0, 3]
    assert spans(res)["乙"] == [0, 3]
    assert spans(res)["丙"] == [1, 4]


def test_contained_takes_precedence_over_duplicate():
    # 同时「被更长页包含」且「同文重复」时优先记为包含
    res = assemble_fragments(F(甲="abcde", 乙="abc", 丙="abc"))
    assert statuses(res) == [STATUS_ASSEMBLED, STATUS_CONTAINED, STATUS_CONTAINED]
    assert res["participant_count"] == 1
    assert res["text"] == "abcde"
    assert order_indices(res) == [1]


def test_whitespace_and_punctuation_participate():
    # 空白与标点原样参与：「a， 」与「， b」重叠「， 」两码点
    res = assemble_fragments(F(甲="a， ", 乙="， b"))
    assert res["text"] == "a， b"
    assert res["length"] == 4
    assert [step["overlap"] for step in res["order"]] == [0, 2]
    assert spans(res) == {"甲": [0, 3], "乙": [1, 4]}
    # 不做规范化：仅半角逗号时不重叠
    res2 = assemble_fragments(F(甲="a, ", 乙="， b"))
    assert res2["total_overlap"] == 0
    assert res2["length"] == 6


def test_earliest_span_for_participant():
    # 参与页「bcab」的合并块起点为 3（aab→abc(重2)→bcab(重2)），
    # 但其全文「bcab」在拼合全文 aabcab 中最早出现在位置 2（跨接缝），
    # span 须取最早出现位置 [2,6) 而非块起点。
    res = assemble_fragments(F(甲="aab", 乙="bcab", 丙="abc"))
    assert res["text"] == "aabcab"
    assert res["length"] == 6
    assert [step["overlap"] for step in res["order"]] == [0, 2, 2]
    assert order_names(res) == ["甲", "丙", "乙"]
    assert spans(res) == {"甲": [0, 3], "丙": [1, 4], "乙": [2, 6]}
    assert res["text"][2:6] == "bcab"


def test_single_participant():
    # 其余全部被包含时只剩一张参与页，全文即该页
    res = assemble_fragments(F(甲="abcdef", 乙="abc", 丙="def"))
    assert statuses(res) == [
        STATUS_ASSEMBLED,
        STATUS_CONTAINED,
        STATUS_CONTAINED,
    ]
    assert res["participant_count"] == 1
    assert res["text"] == "abcdef"
    assert res["length"] == 6
    assert res["total_overlap"] == 0
    assert order_indices(res) == [1]
    assert spans(res)["甲"] == [0, 6]
    assert spans(res)["乙"] == [0, 3]
    assert spans(res)["丙"] == [3, 6]


def test_two_pages():
    res = assemble_fragments(F(甲="天地玄黄", 乙="宇宙洪荒"))
    assert res["text"] == "天地玄黄宇宙洪荒"
    assert res["participant_count"] == 2
    assert order_indices(res) == [1, 2]
    assert [step["overlap"] for step in res["order"]] == [0, 0]


def run_all():
    for name, fn in sorted(
        ((k, v) for k, v in globals().items() if k.startswith("test_")),
        key=lambda kv: kv[0],
    ):
        fn()
        print(f"PASS {name}")
    print("全部测试通过。")


if __name__ == "__main__":
    run_all()
