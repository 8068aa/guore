#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""市场温度计 · 每交易日 15:50 自动更新（巴菲特指数/平均股价/成交额）"""
import hashlib, json, ast, os, re, datetime, urllib.request, http.cookiejar

BASE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(BASE, "state"); os.makedirs(STATE, exist_ok=True)

def ts(d): return int(datetime.datetime.strptime(d, "%Y-%m-%d").timestamp() * 1000)

def sina_snapshot():
    rows, page = [], 1
    while True:
        url = ("https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
               f"Market_Center.getHQNodeData?page={page}&num=100&node=hs_a&sort=amount&asc=0")
        try:
            b = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn/stock/"}),
                timeout=15).read().decode("gbk", "ignore"))
        except Exception:
            return None
        if not b: break
        rows.extend(b); page += 1
    trades = [float(r["trade"]) for r in rows if float(r["trade"]) > 0]
    total_yi = round(sum(float(r["amount"]) for r in rows) / 1e8)
    return {"avgPrice": round(sum(trades) / len(trades), 2), "totalYi": total_yi, "n": len(trades)}

def legulegu(paths):
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.open(urllib.request.Request("https://www.legulegu.com/stockdata",
        headers={"User-Agent": "Mozilla/5.0"}), timeout=20)
    today = datetime.date.today()
    for delta in (0, -1, 1):
        token = hashlib.md5((today + datetime.timedelta(days=delta)).strftime("%Y-%m-%d").encode()).hexdigest()
        try:
            out = {}
            for name, path in paths.items():
                url = "https://www.legulegu.com" + path + ("&" if "?" in path else "?") + "token=" + token
                out[name] = json.loads(op.open(urllib.request.Request(url, headers={
                    "User-Agent": "Mozilla/5.0", "Referer": "https://www.legulegu.com/stockdata"}), timeout=60).read())
            return out
        except Exception:
            continue
    return {}

def append_jl(fn, rec):
    rows = {}
    if os.path.exists(fn):
        for line in open(fn, encoding="utf-8"):
            if line.strip(): r = json.loads(line); rows[r["date"]] = r
    rows[rec["date"]] = rec
    with open(fn, "w", encoding="utf-8") as f:
        for d in sorted(rows): f.write(json.dumps(rows[d], ensure_ascii=False) + "\n")
    return rows

def main():
    today = datetime.date.today().strftime("%Y-%m-%d")
    P = {}
    # ① 巴菲特
    d = legulegu({"b": "/api/stockdata/marketcap-gdp/get-marketcap-gdp"})
    if "b" in d:
        buff = ast.literal_eval(d["b"]["data"])
        S = [[ts(x["date"]), round(x["marketCap"] / x["gdp"] * 100, 2)] for x in buff if x.get("gdp")]
        P["buffett"] = {"base": S[0][0], "days": [(x[0] - S[0][0]) // 86400000 for x in S], "val": [x[1] for x in S]}
    # ② 成交额基线(乐咕拥挤度接口) + ③ 新浪每日：平均股价&成交额
    avg_rows, amt_rows = {}, {}
    if os.path.exists(os.path.join(STATE, "avg_price.jsonl")):
        for line in open(os.path.join(STATE, "avg_price.jsonl"), encoding="utf-8"):
            if line.strip(): r = json.loads(line); avg_rows[r["date"]] = r["v"]
    if os.path.exists(os.path.join(STATE, "amount.jsonl")):
        for line in open(os.path.join(STATE, "amount.jsonl"), encoding="utf-8"):
            if line.strip(): r = json.loads(line); amt_rows[r["date"]] = r["v"]
    d2 = legulegu({"c": "/api/stockdata/ashares-congestion"})
    if "c" in d2:
        for x in d2["c"]["items"]:
            if x.get("totalAmountYi") and x.get("date"):
                amt_rows[x["date"]] = round(x["totalAmountYi"] / 10000, 3)
    snap = sina_snapshot()
    if snap:
        avg_rows[today] = snap["avgPrice"]
        amt_rows[today] = round(snap["totalYi"] / 10000, 3)
    with open(os.path.join(STATE, "avg_price.jsonl"), "w", encoding="utf-8") as f:
        for dd in sorted(avg_rows): f.write(json.dumps({"date": dd, "v": avg_rows[dd]}) + "\n")
    with open(os.path.join(STATE, "amount.jsonl"), "w", encoding="utf-8") as f:
        for dd in sorted(amt_rows): f.write(json.dumps({"date": dd, "v": amt_rows[dd]}) + "\n")
    def pack(rows):
        ks = sorted(rows)
        return {"base": ts(ks[0]), "days": [(ts(k) - ts(ks[0])) // 86400000 for k in ks], "val": [rows[k] for k in ks]}
    P["avgPrice"] = pack(avg_rows)
    P["amount"] = pack(amt_rows)
    # 统计
    ST = {}
    for k in ("buffett", "amount", "avgPrice"):
        v = P[k]["val"]; hi, lo = max(v), min(v)
        di = P[k]["days"]; base = P[k]["base"]
        fd = lambda i: datetime.datetime.fromtimestamp((base + di[i] * 86400000) / 1000).strftime("%Y-%m-%d")
        ST[k] = [hi, fd(v.index(hi)), lo, fd(v.index(lo))]
    # 重写 index.html
    h = open(os.path.join(BASE, "index.html"), encoding="utf-8").read()
    new_head = ("var P = " + json.dumps(P, separators=(",", ":")) + ", ST = "
                + json.dumps(ST, ensure_ascii=False) + ";\nvar META")
    h2 = re.sub(r"var P = .*?;\s*var META", lambda m: new_head, h, count=1, flags=re.S)
    if h2 == h:
        print("警告：index.html 结构未匹配，未更新"); return
    h = h2
    h = re.sub(r"截至 \d{4}-\d{2}-\d{2}", "截至 " + max(max(avg_rows), max(amt_rows), today), h)
    open(os.path.join(BASE, "index.html"), "w", encoding="utf-8").write(h)
    print("更新完成:", {k: v["val"][-1] for k, v in P.items()})

if __name__ == "__main__":
    main()
