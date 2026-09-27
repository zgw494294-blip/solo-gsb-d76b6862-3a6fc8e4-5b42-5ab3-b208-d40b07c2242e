"""残页次序证据：把「A 先于 B」的主张视作有向边，检测冲突闭环并推导必然先后。

规则
----
- 沿用残页拼合模块当前 2～8 张残页的**名称与录入顺序**；主张 0～20 条，
  每条为「before 先于 after」。录入即拒绝三类不合法主张：
  **自指**（before 与 after 为同一页）、**同向重复**（同一对页同方向的
  重复主张）与**未知页名**。
- **文字重叠不算先后证据**：残页文字完全不参与分析，仅以名称定位端点。
- 主张为有向边。**有环时返回边数最少的冲突闭环**（简单有向环）；并列时
  将每个闭环从其**最小主张序号**起旋转，取主张序号序列**字典序最小**者。
- **无环时**对每对残页给出结论：一方可沿主张边到达另一方即**必然先后**，
  证明链取**主张数最少**者，同长取主张序号序列（自先者向后者排列）
  **字典序最小**者；互不可达标为**未定**。
"""

MAX_ORDER_CLAIMS = 20

STATUS_ORDERED = "ordered"
STATUS_UNDECIDED = "undecided"


class OrderEvidenceError(ValueError):
    """主张不合法（自指、同向重复、未知页名或数量越界）。"""


def _page_ref(index: int, name: str) -> dict:
    return {"index": index + 1, "name": name}


def _claim_ref(k: int, u: int, v: int, names: list) -> dict:
    """第 k 条主张（k 为 1 起录入序号）的回显：序号与两端页（录入序号、名称）。"""
    return {
        "index": k,
        "before": _page_ref(u, names[u]),
        "after": _page_ref(v, names[v]),
    }


def _resolve_claims(fragments: list, claims: list):
    """校验主张并解析为 (主张序号1起, 起点, 终点) 的有向边列表。"""
    names = [f["name"] for f in fragments]
    index_of = {name: i for i, name in enumerate(names)}

    if len(claims) > MAX_ORDER_CLAIMS:
        raise OrderEvidenceError(
            f"主张数量最多为 {MAX_ORDER_CLAIMS} 条（当前 {len(claims)} 条）"
        )

    edges = []
    seen = {}  # (起点, 终点) -> 首次出现的主张序号
    for pos, c in enumerate(claims, start=1):
        before = c.get("before", "")
        after = c.get("after", "")
        for raw in (before, after):
            if raw not in index_of:
                label = raw or "（空）"
                raise OrderEvidenceError(f"主张 {pos} 引用了未知页名：{label}")
        u = index_of[before]
        v = index_of[after]
        if u == v:
            raise OrderEvidenceError(
                f"主张 {pos} 自指：残页「{names[u]}」不能先于自身"
            )
        if (u, v) in seen:
            raise OrderEvidenceError(
                f"主张 {pos} 与主张 {seen[(u, v)]} 同向重复"
                f"（「{names[u]}」先于「{names[v]}」）"
            )
        seen[(u, v)] = pos
        edges.append((pos, u, v))
    return names, edges


def _min_rotation(seq: tuple) -> tuple:
    """把序列旋转至从最小元素开始（各元素互异，旋转位置唯一）。"""
    r = min(range(len(seq)), key=seq.__getitem__)
    return seq[r:] + seq[:r]


def _shortest_cycle(n: int, edges: list):
    """求边数最少的简单有向环；并列取旋转后主张序号序列字典序最小者。

    用「环内最小顶点」去重枚举：以每个顶点 s 为环内编号最小者做 DFS，
    途中只允许经过编号大于 s 且未在当前路径上的顶点；指回 s 的边闭合
    一个环。n ≤ 8、边 ≤ 20，枚举量可忽略。
    返回 (最优键, 按最优旋转排好的主张序号元组)；无环返回 None。
    """
    adj = [[] for _ in range(n)]
    for k, u, v in edges:
        adj[u].append((v, k))

    best_key = None
    best_rot = None

    def consider(edge_seq):
        nonlocal best_key, best_rot
        rot = _min_rotation(tuple(edge_seq))
        key = (len(rot), rot)
        if best_key is None or key < best_key:
            best_key = key
            best_rot = rot

    for s in range(n):
        def dfs(u, used, path):
            for w, k in adj[u]:
                if w == s:
                    consider(path + [k])
                elif w > s and not (used & (1 << w)):
                    dfs(w, used | (1 << w), path + [k])

        dfs(s, 1 << s, [])

    return None if best_rot is None else (best_key, best_rot)


def _toposort(n: int, adj: list) -> list:
    """Kahn 拓扑序；候选顶点并列时取录入序号小者（结果不受其影响，仅为确定）。"""
    indeg = [0] * n
    for u in range(n):
        for v, _ in adj[u]:
            indeg[v] += 1
    ready = [v for v in range(n) if indeg[v] == 0]
    order = []
    while ready:
        u = min(ready)
        ready.remove(u)
        order.append(u)
        for v, _ in adj[u]:
            indeg[v] -= 1
            if indeg[v] == 0:
                ready.append(v)
    return order


def _best_from(source: int, topo: list, adj: list):
    """DAG 中 source 到各可达顶点的最短证明链。

    返回 {目标顶点: (长度, 主张序号元组)}；同长取序号序列字典序最小。
    按拓扑序松弛：处理 v 时其所有前驱均已定型，故到 v 的最优解已最终确定。
    """
    dist = {source: 0}
    seq = {source: ()}
    for v in topo:
        if v not in dist:
            continue
        for w, k in sorted(adj[v]):
            cand_len = dist[v] + 1
            cand_seq = seq[v] + (k,)
            old_len = dist.get(w)
            if old_len is None or (cand_len, cand_seq) < (old_len, seq[w]):
                dist[w] = cand_len
                seq[w] = cand_seq
    return dist, seq


def analyze_order_evidence(fragments: list, claims: list) -> dict:
    """分析残页次序主张。

    fragments 为 [{"name", "text"}, …]（已校验：2～8 张、名称不重复），
    claims 为 [{"before", "after"}, …]（名称已去空白，0～20 条），顺序即
    主张录入顺序。返回：

      {"claim_count", "claims"（回显，含主张序号与两端页）,
       "acyclic", "cycle"（有环时）, "pairs"（无环时）}

    不合法主张抛 OrderEvidenceError。
    """
    names, edges = _resolve_claims(fragments, claims)
    n = len(fragments)
    claim_refs = [_claim_ref(k, u, v, names) for k, u, v in edges]

    result = {
        "claim_count": len(edges),
        "claims": claim_refs,
        "acyclic": True,
        "cycle": None,
        "pairs": None,
    }

    cycle = _shortest_cycle(n, edges)
    if cycle is not None:
        _, rotated = cycle
        edge_of = {k: (u, v) for k, u, v in edges}
        # 旋转后相邻主张首尾相接：pages[i] 为第 i 条主张的起点，
        # 其终点恰为 pages[(i+1) % L]。
        pages = []
        for k in rotated:
            u, _ = edge_of[k]
            pages.append(_page_ref(u, names[u]))
        result["acyclic"] = False
        result["cycle"] = {
            "edge_count": len(rotated),
            "claims": [
                _claim_ref(k, edge_of[k][0], edge_of[k][1], names) for k in rotated
            ],
            "pages": pages,
        }
        return result

    # 无环：每对残页判定必然先后或未定，并给主张数最少的证明链。
    adj = [[] for _ in range(n)]
    for k, u, v in edges:
        adj[u].append((v, k))
    topo = _toposort(n, adj)
    best = [_best_from(s, topo, adj) for s in range(n)]

    edge_lookup = {k: (u, v) for k, u, v in edges}
    pairs = []
    for i in range(n):
        for j in range(i + 1, n):
            pair = {"a": _page_ref(i, names[i]), "b": _page_ref(j, names[j])}
            if j in best[i][0]:
                chain = best[i][1][j]
                pair.update(
                    status=STATUS_ORDERED,
                    earlier=_page_ref(i, names[i]),
                    later=_page_ref(j, names[j]),
                    claim_count=len(chain),
                    proof=[
                        _claim_ref(k, edge_lookup[k][0], edge_lookup[k][1], names)
                        for k in chain
                    ],
                )
            elif i in best[j][0]:
                chain = best[j][1][i]
                pair.update(
                    status=STATUS_ORDERED,
                    earlier=_page_ref(j, names[j]),
                    later=_page_ref(i, names[i]),
                    claim_count=len(chain),
                    proof=[
                        _claim_ref(k, edge_lookup[k][0], edge_lookup[k][1], names)
                        for k in chain
                    ],
                )
            else:
                pair.update(
                    status=STATUS_UNDECIDED,
                    earlier=None,
                    later=None,
                    claim_count=0,
                    proof=[],
                )
            pairs.append(pair)

    result["pairs"] = pairs
    return result
