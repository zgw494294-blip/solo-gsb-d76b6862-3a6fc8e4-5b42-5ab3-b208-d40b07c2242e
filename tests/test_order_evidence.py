"""残页次序证据规则测试。

直接运行：python tests/test_order_evidence.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.order_evidence import (  # noqa: E402
    MAX_ORDER_CLAIMS,
    OrderEvidenceError,
    STATUS_ORDERED,
    STATUS_UNDECIDED,
    analyze_order_evidence,
)


def F(names):
    return [{"name": n, "text": n} for n in names]


def C(a, b):
    return {"before": a, "after": b}


def claim_indices(pair):
    return [c["index"] for c in pair["proof"]]


def pair_map(res):
    return {(p["a"]["name"], p["b"]["name"]): p for p in res["pairs"]}


def test_no_claims_all_undecided():
    res = analyze_order_evidence(F(["甲", "乙", "丙"]), [])
    assert res["acyclic"] is True
    assert res["cycle"] is None
    assert res["claim_count"] == 0
    assert len(res["pairs"]) == 3
    assert all(p["status"] == STATUS_UNDECIDED for p in res["pairs"])
    assert all(p["earlier"] is None and p["proof"] == [] for p in res["pairs"])


def test_direct_and_transitive_order():
    res = analyze_order_evidence(
        F(["甲", "乙", "丙", "丁"]),
        [C("甲", "乙"), C("乙", "丙"), C("甲", "丁")],
    )
    assert res["acyclic"] is True
    pm = pair_map(res)
    # 直接主张
    p = pm[("甲", "乙")]
    assert p["status"] == STATUS_ORDERED
    assert p["earlier"]["name"] == "甲" and p["later"]["name"] == "乙"
    assert p["claim_count"] == 1 and claim_indices(p) == [1]
    # 传递推出，证明链 1→2
    p = pm[("甲", "丙")]
    assert p["earlier"]["name"] == "甲" and p["later"]["name"] == "丙"
    assert claim_indices(p) == [1, 2]
    assert [c["before"]["name"] for c in p["proof"]] == ["甲", "乙"]
    assert [c["after"]["name"] for c in p["proof"]] == ["乙", "丙"]
    # 无路径者未定
    assert pm[("乙", "丁")]["status"] == STATUS_UNDECIDED
    assert pm[("丙", "丁")]["status"] == STATUS_UNDECIDED
    # 反向对的证明链方向：录入顺序在后的页也可作先者
    p = pm[("乙", "丙")]
    assert p["earlier"]["index"] == 2 and p["later"]["index"] == 3


def test_shortest_proof_prefers_fewer_claims():
    # 直连（3）比两跳（1,2）主张数少
    res = analyze_order_evidence(
        F(["甲", "乙", "丙"]), [C("甲", "乙"), C("乙", "丙"), C("甲", "丙")]
    )
    p = pair_map(res)[("甲", "丙")]
    assert claim_indices(p) == [3]


def test_shortest_proof_lexicographic_tie():
    # 甲→丁 两条等长（2 条主张）路径：1,3 与 2,4，取序号序列字典序小者
    res = analyze_order_evidence(
        F(["甲", "乙", "丙", "丁"]),
        [C("甲", "乙"), C("甲", "丙"), C("乙", "丁"), C("丙", "丁")],
    )
    p = pair_map(res)[("甲", "丁")]
    assert p["claim_count"] == 2
    assert claim_indices(p) == [1, 3]


def test_lex_tie_second_edge_decides():
    # 甲→丁 有两条两跳路径：1,2 与 5,6，首元素即 1<5，取 1,2。
    res = analyze_order_evidence(
        F(["甲", "乙", "丙", "丁", "戊"]),
        [
            C("甲", "乙"),  # 1
            C("乙", "丁"),  # 2 -> 路径 1,2
            C("乙", "丙"),  # 3
            C("丙", "丁"),  # 4 -> 路径 1,3,4（三跳，不并列）
            C("甲", "戊"),  # 5
            C("戊", "丁"),  # 6 -> 路径 5,6
        ],
    )
    assert claim_indices(pair_map(res)[("甲", "丁")]) == [1, 2]


def test_two_cycle():
    res = analyze_order_evidence(F(["甲", "乙"]), [C("甲", "乙"), C("乙", "甲")])
    assert res["acyclic"] is False
    cyc = res["cycle"]
    assert cyc["edge_count"] == 2
    assert [c["index"] for c in cyc["claims"]] == [1, 2]
    assert [p["name"] for p in cyc["pages"]] == ["甲", "乙"]


def test_shortest_cycle_preferred():
    # 同时存在三环 1,2,3 与更长环；返回最短者
    res = analyze_order_evidence(
        F(["甲", "乙", "丙", "丁"]),
        [
            C("甲", "乙"),  # 1
            C("乙", "丙"),  # 2
            C("丙", "甲"),  # 3 -> 三环
            C("甲", "丁"),  # 4
            C("丁", "乙"),  # 5 -> 四环 4,5,2,3
        ],
    )
    assert res["acyclic"] is False
    cyc = res["cycle"]
    assert cyc["edge_count"] == 3
    assert [c["index"] for c in cyc["claims"]] == [1, 2, 3]
    # 环页首尾相接：每条主张起点为 pages[i]，终点为 pages[i+1]
    pages = cyc["pages"]
    for i, claim in enumerate(cyc["claims"]):
        assert claim["before"]["name"] == pages[i]["name"]
        assert claim["after"]["name"] == pages[(i + 1) % len(pages)]["name"]


def test_cycle_rotated_to_smallest_index():
    # 录入顺序不以环内最小序号开头；返回结果须从最小主张序号旋转
    res = analyze_order_evidence(
        F(["甲", "乙", "丙"]), [C("乙", "丙"), C("丙", "甲"), C("甲", "乙")]
    )
    cyc = res["cycle"]
    assert [c["index"] for c in cyc["claims"]] == [1, 2, 3]
    assert [p["name"] for p in cyc["pages"]] == ["乙", "丙", "甲"]


def test_cycle_lexicographic_tie():
    # 两个等长（均 2 条边）的环：甲⇄乙（主张 1,4）与 丙⇄丁（主张 2,3）。
    # 旋转后序号序列分别为 (1,4) 与 (2,3)，取字典序小者 (1,4)。
    res = analyze_order_evidence(
        F(["甲", "乙", "丙", "丁"]),
        [
            C("甲", "乙"),  # 1
            C("丙", "丁"),  # 2
            C("丁", "丙"),  # 3
            C("乙", "甲"),  # 4
        ],
    )
    assert res["acyclic"] is False
    cyc = res["cycle"]
    assert cyc["edge_count"] == 2
    assert [c["index"] for c in cyc["claims"]] == [1, 4]
    assert [p["name"] for p in cyc["pages"]] == ["甲", "乙"]


def test_cycle_rotation_changes_lex_order():
    # 两个三环，边序号集合相同不可行，故用不同集合构造并列：
    # 环一 1,5,6（旋转 (1,5,6)）；环二 2,3,4（旋转 (2,3,4)）。取 (1,5,6)。
    res = analyze_order_evidence(
        F(["甲", "乙", "丙", "丁", "戊"]),
        [
            C("甲", "乙"),  # 1 环一
            C("乙", "丙"),  # 2 环二
            C("丙", "丁"),  # 3 环二
            C("丁", "乙"),  # 4 环二闭合（乙→丙→丁→乙）
            C("乙", "戊"),  # 5 环一
            C("戊", "甲"),  # 6 环一闭合（甲→乙→戊→甲）
        ],
    )
    assert res["acyclic"] is False
    cyc = res["cycle"]
    assert cyc["edge_count"] == 3
    assert [c["index"] for c in cyc["claims"]] == [1, 5, 6]


def test_self_reference_rejected():
    try:
        analyze_order_evidence(F(["甲", "乙"]), [C("甲", "乙"), C("乙", "乙")])
        assert False, "自指应被拒绝"
    except OrderEvidenceError as exc:
        assert "自指" in str(exc) and "主张 2" in str(exc)


def test_same_direction_duplicate_rejected():
    try:
        analyze_order_evidence(
            F(["甲", "乙"]), [C("甲", "乙"), C("甲", "乙")]
        )
        assert False, "同向重复应被拒绝"
    except OrderEvidenceError as exc:
        assert "同向重复" in str(exc) and "主张 1" in str(exc)


def test_opposite_direction_allowed_as_cycle():
    # 反向不是同向重复，合法录入并构成二环
    res = analyze_order_evidence(F(["甲", "乙"]), [C("甲", "乙"), C("乙", "甲")])
    assert res["acyclic"] is False


def test_unknown_page_name_rejected():
    for bad in [C("甲", "X"), C("X", "甲"), C("", "甲")]:
        try:
            analyze_order_evidence(F(["甲", "乙"]), [bad])
            assert False, f"未知页名应被拒绝：{bad}"
        except OrderEvidenceError as exc:
            assert "未知页名" in str(exc)


def test_too_many_claims_rejected():
    # 8 张页共 56 条有向非自指页对，可构造 21 条互不重复的合法主张
    names = [f"页{i}" for i in range(8)]
    pairs = [(names[i], names[j]) for i in range(8) for j in range(8) if i != j]
    claims = [C(a, b) for a, b in pairs[: MAX_ORDER_CLAIMS + 1]]
    try:
        analyze_order_evidence(F(names), claims)
        assert False, "超过 20 条主张应被拒绝"
    except OrderEvidenceError as exc:
        assert str(MAX_ORDER_CLAIMS) in str(exc)


def test_text_overlap_is_not_evidence():
    # 残页文字即便有最长重叠，也不产生先后方向：无主张时全部未定
    res = analyze_order_evidence(
        [{"name": "甲", "text": "道可道非常"}, {"name": "乙", "text": "非常名"}],
        [],
    )
    assert all(p["status"] == STATUS_UNDECIDED for p in res["pairs"])


def test_claim_echo_contains_indices_and_names():
    res = analyze_order_evidence(
        F(["甲", "乙"]), [C("乙", "甲")]
    )
    c = res["claims"][0]
    assert c["index"] == 1
    assert c["before"] == {"index": 2, "name": "乙"}
    assert c["after"] == {"index": 1, "name": "甲"}
    # 无环：乙先于甲（录入顺序在后亦可推出）
    p = pair_map(res)[("甲", "乙")]
    assert p["earlier"]["name"] == "乙" and p["later"]["name"] == "甲"
    assert claim_indices(p) == [1]


def test_pair_order_follows_entry_order():
    # pairs 按「录入序号 i<j」逐对列出
    res = analyze_order_evidence(
        F(["丁", "丙", "乙", "甲"]), [C("丁", "甲")]
    )
    keys = [(p["a"]["index"], p["b"]["index"]) for p in res["pairs"]]
    assert keys == [(1, 2), (1, 3), (1, 4), (2, 3), (2, 4), (3, 4)]


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
