import asyncio, json, re, sys
from playwright.async_api import async_playwright
URL = "https://public.tableau.com/views/vl_Export_of_Agriproducts_v2/Dashboard1?:embed=y&:showVizHome=no"
TR = ("Авто", "Залізничний", "Паром", "Порти")

async def grab():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": 1600, "height": 1100})
        got = {}
        async def onresp(r):
            if "bootstrapSession" in r.url:
                got["status"] = r.status
                got["body"] = (await r.body()).decode("utf8", "replace")
        pg.on("response", onresp)
        resp = await pg.goto(URL, wait_until="domcontentloaded", timeout=90000)
        print("page status:", resp.status if resp else None)
        for _ in range(40):
            if "body" in got: break
            await pg.wait_for_timeout(1000)
        title = await pg.title()
        print("title:", title)
        await b.close()
        return got

def decode(s):
    i = 0; o = []
    while i < len(s):
        m = re.match(r"(\d+);", s[i:])
        if not m: break
        n = int(m.group(1)); st = i + m.end()
        o.append(json.loads(s[st:st + n])); i = st + n
    return o

def build(body):
    o = decode(body)
    sec = o[1]["secondaryInfo"]["presModelMap"]
    dd = sec["dataDictionary"]["presModelHolder"]["genDataDictionaryPresModel"]["dataSegments"]["0"]["dataColumns"]
    T = {c["dataType"]: c["dataValues"] for c in dd}
    pm = sec["vizData"]["presModelHolder"]["genPresModelMapPresModel"]["presModelMap"]
    def table(name, spec):
        v = pm[name]["presModelHolder"]["genVizDataPresModel"]["paneColumnsData"]["paneColumnsList"][0]["vizPaneColumns"]
        n = max(len(v[i]["aliasIndices"]) or len(v[i]["valueIndices"]) for i in range(1, len(v)))
        rows = []
        for r in range(n):
            row = []
            for ci, t in spec:
                c = v[ci]
                if t == "m": row.append(T["integer"][c["valueIndices"][r]])
                elif t == "s": row.append(T["cstring"][c["aliasIndices"][r]])
                else:
                    a = c["aliasIndices"][r]; row.append(T["real"][a] if a >= 0 else 0.0)
            rows.append(tuple(row))
        return rows
    t7 = table("Sheet 7", [(1, "m"), (2, "s"), (3, "r")])
    t32 = table("Sheet 3 (2)", [(1, "m"), (2, "s"), (3, "r")])
    ts = table("трансчастка", [(1, "m"), (2, "s"), (3, "s"), (4, "r")])
    tr = {(m, t): v for m, t, v in t32}
    prod = {(m, p): v for m, p, v in t7}
    cell = {(m, p, t): sh * tr[(m, t)] for m, p, t, sh in ts}
    return prod, tr, cell

def main():
    got = asyncio.run(grab())
    print("bootstrap status:", got.get("status"), "bytes:", len(got.get("body", "")))
    if "body" not in got:
        print("FAIL: no data (blocked?)"); sys.exit(1)
    prod, tr, cell = build(got["body"])
    months = sorted({m for m, _ in prod})
    print("months:", len(months), months[0], months[-1])
    print("grand total:", round(sum(prod.values())))
    d = max(abs(sum(cell.get((m, p, t), 0) for t in TR) - v) for (m, p), v in prod.items())
    print("max diff product vs transports:", d)
    print("March2022 corn:", [round(cell.get((202203, "Кукурудза", t), 0)) for t in TR])
    with open("out.csv", "w", encoding="utf-8") as f:
        f.write("month,product,all,auto,rail,ferry,ports\n")
        for (m, p), v in sorted(prod.items()):
            f.write(f"{m},{p},{round(v)}," + ",".join(str(round(cell.get((m, p, t), 0))) for t in TR) + "\n")
    print("OK rows:", len(prod))

main()
