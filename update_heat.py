#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""市场过热指标 · 每日收盘后自动更新（建议 15:50 运行）"""
import hashlib, json, ast, math, os, datetime, urllib.request, http.cookiejar

BASE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(BASE, "state"); os.makedirs(STATE, exist_ok=True)
TURN = os.path.join(STATE, "turnover.jsonl")
UA = {"User-Agent": "Mozilla/5.0"}

def legulegu(paths):
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.open(urllib.request.Request("https://www.legulegu.com/stockdata", headers=UA), timeout=20)
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

def sina_turnover():
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
    amt = sum(float(r["amount"]) for r in rows); nmc = sum(float(r["nmc"]) for r in rows)
    return round(amt / (nmc * 10000) * 100, 2)


def bond10_today():
    """中债官网当日10年期国债收益率"""
    try:
        req = urllib.request.Request(
            "https://yield.chinabond.com.cn/cbweb-mn/search/financialTime?workTime=" +
            datetime.date.today().strftime("%Y-%m-%d"),
            data=b"", headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120",
                               "Referer": "https://yield.chinabond.com.cn/cbweb-mn/graph/financial_time",
                               "X-Requested-With": "XMLHttpRequest"})
        d = json.loads(urllib.request.urlopen(req, timeout=25).read().decode("utf-8","ignore"))
        if d and isinstance(d[0], list): d = d[0]
        for curve in d:
            for tenor, val in curve.get("seriesData", []):
                if abs(float(tenor) - 10.0) < 1e-9: return val
    except Exception:
        pass
    return None

def load_bond_series():
    p = os.path.join(STATE, "bond10_series.json")
    return json.load(open(p)) if os.path.exists(p) else {}

def main():
    d = legulegu({"pe800": "/api/stockdata/index-basic-pe?indexCode=000906.SH",
                  "peAll": "/api/stock-data/market-ttm-lyr?marketId=5",
                  "buffett": "/api/stockdata/marketcap-gdp/get-marketcap-gdp",
                  "deposit": "/api/stockdata/market-cap-deposit-ratio"})
    def ts(x): return int(datetime.datetime(*map(int, x.split("-"))).timestamp() * 1000)
    S = {}
    if "pe800" in d: S["pe800"] = [[ts(x["date"]), round(x["ttmPe"], 2)] for x in ast.literal_eval(d["pe800"]["data"]) if x.get("ttmPe")]
    if "peAll" in d: S["peAll"] = [[ts(x["date"]), round(x["middlePETTM"], 2)] for x in ast.literal_eval(d["peAll"]["data"]) if x.get("middlePETTM")]
    if "buffett" in d: S["buffett"] = [[ts(x["date"]), round(x["marketCap"] / x["gdp"] * 100, 2)] for x in ast.literal_eval(d["buffett"]["data"]) if x.get("gdp")]
    if "deposit" in d:
        dep = [(p["date"], p.get("value")) for p in d["deposit"]["points"] if p.get("value") is not None]
        S["deposit"] = [[ts(a), round(b * 100, 2)] for a, b in dep]
        if d["deposit"].get("latestRatio"): S["deposit"].append([ts(d["deposit"]["updatedDate"]), round(d["deposit"]["latestRatio"] * 100, 2)])
    # 换手率：本地累积 + 今日
    tv = {}
    if os.path.exists(TURN):
        for line in open(TURN, encoding="utf-8"):
            if line.strip(): r = json.loads(line); tv[r["date"]] = r["v"]
    if datetime.date.today().weekday() < 5:
        today = datetime.date.today().strftime("%Y-%m-%d")
        cur = sina_turnover()
        if cur is not None and tv.get(today) != cur:
            tv[today] = cur
            open(TURN, "a", encoding="utf-8").write(json.dumps({"date": today, "v": cur}, ensure_ascii=False) + "\n")
    S["turnover"] = sorted([[ts(k), v] for k, v in tv.items()])
    # 国债收益率：本地序列 + 今日追加，计算格雷厄姆/股债利差
    bond = load_bond_series()
    y10 = bond10_today()
    today = datetime.date.today().strftime("%Y-%m-%d")
    if y10 is not None and bond.get(today) != y10:
        bond[today] = y10
        json.dump(bond, open(os.path.join(STATE, "bond10_series.json"), "w"))
    if "peAll" in S:
        import pandas as _pd
        bser = _pd.Series(bond, dtype="float64").sort_index().ffill()
        g, er = [], []
        for ts_v, pe in S["peAll"]:
            d = _pd.Timestamp(ts_v, unit="ms").strftime("%Y-%m-%d")
            dd = d if d in bser.index else bser.index[bser.index <= d][-1] if (bser.index <= d).any() else None
            if dd is None or _pd.isna(bser[dd]): continue
            ep = 1.0 / pe; y = bser[dd] / 100.0
            g.append([ts_v, round(ep / y, 3)]); er.append([ts_v, round((ep - y) * 100, 3)])
        if g: S["graham"] = g
        if er: S["erp"] = er
    if not S: print("无数据，退出"); return
    asof = max(datetime.datetime.fromtimestamp(v[-1][0] / 1000).strftime("%Y-%m-%d") for v in S.values())
    import build_heat_html
    build_heat_html.render(S, asof, os.path.join(BASE, "index.html"))
    json.dump(S, open(os.path.join(STATE, "last_series.json"), "w"), separators=(",", ":"))
    print("更新完成:", asof, {k: v[-1][1] for k, v in S.items()})

if __name__ == "__main__":
    main()
