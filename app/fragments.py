"""残页拼合：按最长后缀—前缀重叠把具名残页拼成最短全文。

规则
----
- 独立录入 2～8 张具名残页，每张 1～100 个 Unicode 码点，名称不重复。
- 原样比较码点：空白与标点照常参与，不做任何规范化。
- 全文被某张**更长页**包含的残页不参与拼接；同文重复页中**录入较晚**者
  也不参与拼接（同时满足两者时优先记为「被更长页包含」）；两类残页仍须
  在拼合全文中定位其最早出现区间。
- 其余残页每张使用一次：对任一排列，相邻两页按前页后缀与后页前缀的
  **最长重叠**（可为零）逐对合并；取**全文码点数最少**的结果，并列先取
  **全文码点字典序最小**者，再取**参与拼接的录入序号序列最小**者。

最优排列用子集动态规划求解：状态 (已用集合, 末页) 只需保留一份最优前缀
——同一末页下后续追加的串只取决于末页与后续排列，故 (全长, 全文, 序号
序列) 逐项压倒的前缀对任何后续都不可能翻案。
"""

from itertools import combinations

STATUS_ASSEMBLED = "assembled"
STATUS_CONTAINED = "contained"
STATUS_DUPLICATE = "duplicate"


def _overlap(a: str, b: str) -> int:
    """a 的后缀与 b 的前缀的最长重叠长度（可为 0；原样逐码点比较）。"""
    limit = min(len(a), len(b))
    for length in range(limit, 0, -1):
        if a[-length:] == b[:length]:
            return length
    return 0


def _classify(texts: list) -> list:
    """逐张残页判定拼接资格：assembled／contained／duplicate。

    - 任一张更长页（码点严格更多）完整包含其全文 → contained；
    - 否则与录入更早的某张同文 → duplicate（同文只保留最早一张）；
    - 其余 assembled。参与页之间互不为子串，故相邻重叠恒短于两页全文。
    """
    n = len(texts)
    statuses = [STATUS_ASSEMBLED] * n
    for i in range(n):
        if any(
            len(texts[j]) > len(texts[i]) and texts[i] in texts[j]
            for j in range(n)
            if j != i
        ):
            statuses[i] = STATUS_CONTAINED
        elif any(texts[j] == texts[i] for j in range(i)):
            statuses[i] = STATUS_DUPLICATE
    return statuses


def assemble_fragments(fragments: list) -> dict:
    """把具名残页拼成最短全文，并逐张给出最早出现的码点半开区间。

    fragments 为 [{"name", "text"}, …]（已校验：2～8 张、名称不重复、
    每张 1～100 个码点），顺序即录入顺序。返回：

      {"text", "length", "participant_count", "total_overlap",
       "order": [{"index", "name", "overlap"}, …],
       "fragments": [{"index", "name", "length", "status", "span"}, …]}

    order 为参与拼接页的拼接顺序（index 为 1 起录入序号；overlap 为与
    前一页合并所用的最长重叠码点数，首页为 0）；fragments 按录入顺序
    逐张列出，含未参与拼接者，span 为全文中最早出现的 [start, end)。
    """
    names = [f["name"] for f in fragments]
    texts = [f["text"] for f in fragments]
    n = len(fragments)

    statuses = _classify(texts)
    participants = [i for i in range(n) if statuses[i] == STATUS_ASSEMBLED]

    # 参与页两两最长后缀—前缀重叠
    overlaps = [[0] * n for _ in range(n)]
    for i in participants:
        for j in participants:
            if i != j:
                overlaps[i][j] = _overlap(texts[i], texts[j])

    # 子集 DP：state[(mask, last)] = 该路径下的最优
    # (全长, 全文, 录入序号序列)；元组比较即「全长 → 全文字典序 →
    # 序号序列字典序」，与取舍规则一致。
    state = {}
    for i in participants:
        state[(1 << i, i)] = (len(texts[i]), texts[i], (i + 1,))
    full_mask = sum(1 << i for i in participants)
    for size in range(1, len(participants) + 1):
        for group in combinations(participants, size):
            mask = sum(1 << i for i in group)
            for last in group:
                cur = state.get((mask, last))
                if cur is None:
                    continue
                for nxt in participants:
                    if mask & (1 << nxt):
                        continue
                    ov = overlaps[last][nxt]
                    suffix = texts[nxt][ov:]
                    cand = (
                        cur[0] + len(suffix),
                        cur[1] + suffix,
                        cur[2] + (nxt + 1,),
                    )
                    key = (mask | (1 << nxt), nxt)
                    prev = state.get(key)
                    if prev is None or cand < prev:
                        state[key] = cand

    best_length, best_text, best_seq = min(
        state[(full_mask, last)] for last in participants
    )

    # 由最优序号序列回溯各步重叠（首页记 0）
    order = []
    for step, idx1 in enumerate(best_seq):
        idx = idx1 - 1
        if step == 0:
            ov = 0
        else:
            ov = overlaps[best_seq[step - 1] - 1][idx]
        order.append({"index": idx1, "name": names[idx], "overlap": ov})

    # 每张残页（含未参与拼接者）在全文中定位最早出现区间。
    # 参与页逐对合并时必为全文中的连续子串；被包含页／同文页的全文必为
    # 某张参与页的子串（包含链终止于参与页），故必可定位。
    frag_out = []
    for i in range(n):
        start = best_text.find(texts[i])
        frag_out.append(
            {
                "index": i + 1,
                "name": names[i],
                "length": len(texts[i]),
                "status": statuses[i],
                "span": [start, start + len(texts[i])],
            }
        )

    return {
        "text": best_text,
        "length": best_length,
        "participant_count": len(participants),
        "total_overlap": sum(item["overlap"] for item in order),
        "order": order,
        "fragments": frag_out,
    }
