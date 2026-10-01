"""
全部 132 只股票统一主排名报告 (补充版)
复用 long_term_strategy.py 的评分逻辑, 输出一张统一排序表
"""
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np

from long_term_strategy import (
    SECTORS, INDICES, compute_one, score_one, compute_sector_stats, format_pct
)


def main():
    print("\n" + "=" * 80)
    print("  📊 全股票主排名 (132 只)")
    print(f"  生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 80)

    all_tickers = []
    sector_of = {}
    for sec, ticks in SECTORS.items():
        for t in ticks:
            if t not in sector_of:
                all_tickers.append(t)
                sector_of[t] = sec

    print(f"\n分析 {len(all_tickers)} 只标的...")

    raw = {}
    with ThreadPoolExecutor(max_workers=20) as ex:
        futures = {ex.submit(compute_one, t): t for t in all_tickers}
        done = 0
        for fut in as_completed(futures):
            t = futures[fut]
            r = fut.result()
            if r:
                raw[t] = r
            done += 1
            if done % 20 == 0:
                print(f"  已完成 {done}/{len(all_tickers)}")

    print(f"  ✅ 成功: {len(raw)}/{len(all_tickers)}")

    # 打分
    sector_stats_map = {}
    for sec, ticks in SECTORS.items():
        members = [raw[t] for t in ticks if t in raw and '-USD' not in t]
        sector_stats_map[sec] = compute_sector_stats(members) if members else {}

    results = {}
    for t, m in raw.items():
        sec = sector_of.get(t)
        results[t] = score_one(m, sector_stats=sector_stats_map.get(sec))

    # 排序: 评分降序
    all_sorted = sorted(results.values(), key=lambda x: -x['score'])

    # 输出
    out_path = Path(__file__).parent / f"all_stocks_ranking_{datetime.now().strftime('%Y-%m-%d')}.md"
    lines = []
    def p(s=""):
        lines.append(s)
        print(s)

    p(f"# 全部 {len(results)} 只标的主排名 (1 年+ 长线视角)")
    p(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    p()
    p("## 评分维度 (0-100)")
    p("- **趋势质量 20 分**: MA200 + 周线 MA50")
    p("- **动量强度 10 分**: 12M / 6M 回报")
    p("- **基本面 50 分** (Buffett 框架): 营收增长 + 净利率 + 毛利率护城河 + ROE + FCF 收益率 + 估值 PEG/P-E + 同行比较")
    p("- **风险控制 20 分**: 波动率 + 最大回撤 + 负债 + 流动性")
    p()
    p("## 评级区间")
    p("- 🟢 **75+** 买入 / 核心持仓")
    p("- 🟢 **62-74** 增持 / 长线建仓")
    p("- 🟡 **48-61** 持有 / 观望")
    p("- 🟠 **35-47** 减持 / 风险警告")
    p("- 🔴 **<35** 回避 / 重新评估")
    p()

    # 分级统计
    counts = {'buy_core': 0, 'add': 0, 'hold': 0, 'trim': 0, 'avoid': 0}
    for r in all_sorted:
        s = r['score']
        if s >= 75: counts['buy_core'] += 1
        elif s >= 62: counts['add'] += 1
        elif s >= 48: counts['hold'] += 1
        elif s >= 35: counts['trim'] += 1
        else: counts['avoid'] += 1
    p("## 📊 分级统计")
    p()
    p(f"| 评级 | 数量 | 占比 |")
    p(f"|------|------|------|")
    total = len(all_sorted)
    p(f"| 🟢 买入核心 (75+) | {counts['buy_core']} | {counts['buy_core']/total*100:.0f}% |")
    p(f"| 🟢 增持 (62-74) | {counts['add']} | {counts['add']/total*100:.0f}% |")
    p(f"| 🟡 持有 (48-61) | {counts['hold']} | {counts['hold']/total*100:.0f}% |")
    p(f"| 🟠 减持 (35-47) | {counts['trim']} | {counts['trim']/total*100:.0f}% |")
    p(f"| 🔴 回避 (<35) | {counts['avoid']} | {counts['avoid']/total*100:.0f}% |")
    p()

    # 主排名表
    p(f"## 🏆 主排名 (按综合评分降序)")
    p()
    p("| 排名 | 标的 | 板块 | 现价 | 12M | 6M | vs MA200 | 周RSI | 营收增长 | 净利率 | ROE | PEG | 波动率 | 最大回撤 | 评分 | 评级 |")
    p("|------|------|------|------|----|----|---------|-------|---------|-------|-----|-----|--------|----------|------|------|")
    for idx, r in enumerate(all_sorted, 1):
        sec_short = sector_of.get(r['ticker'], '').split(' (')[0]
        vs_ma200 = f"{(r['price']/r['ma200']-1)*100:+.0f}%" if r['ma200'] else "—"
        rsi_s = f"{r['w_rsi']:.0f}" if r['w_rsi'] else "—"
        rg_s = f"{r['rev_growth']*100:+.0f}%" if r['rev_growth'] is not None else "—"
        pm_s = f"{r['profit_margin']*100:.0f}%" if r['profit_margin'] is not None else "—"
        roe_s = f"{r['roe']*100:.0f}%" if r['roe'] is not None else "—"
        peg_s = f"{r['peg']:.2f}" if r['peg'] and r['peg'] > 0 else "—"
        vol_s = f"{r['vol_annual']:.0f}%" if r['vol_annual'] else "—"
        dd_s = f"{r['max_dd']:.0f}%" if r['max_dd'] else "—"
        # 简化评级标签
        rating_tag = r['rating'].split(' / ')[0]
        p(f"| {idx} | **{r['ticker']}** | {sec_short} | ${r['price']:.2f} | "
          f"{format_pct(r['ret_12m'],0)} | {format_pct(r['ret_6m'],0)} | "
          f"{vs_ma200} | {rsi_s} | {rg_s} | {pm_s} | {roe_s} | {peg_s} | "
          f"{vol_s} | {dd_s} | **{r['score']}** | {rating_tag} |")
    p()

    # 板块平均对比
    p("## 📊 板块平均评分对比 (降序)")
    p()
    p("| 板块 | 成员数 | 平均评分 | 平均 12M | 最强标的 | 最弱标的 |")
    p("|------|-------|---------|---------|---------|---------|")
    sector_rows = []
    for sec, ticks in SECTORS.items():
        members = [results[t] for t in ticks if t in results]
        if not members:
            continue
        avg_s = np.mean([m['score'] for m in members])
        avg_ret = np.mean([m['ret_12m'] for m in members if m['ret_12m'] is not None])
        best = max(members, key=lambda x: x['score'])
        worst = min(members, key=lambda x: x['score'])
        sector_rows.append((sec, len(members), avg_s, avg_ret, best, worst))
    sector_rows.sort(key=lambda x: -x[2])
    for sec, n, avg_s, avg_ret, best, worst in sector_rows:
        p(f"| **{sec}** | {n} | {avg_s:.0f} | {avg_ret:+.0f}% | "
          f"{best['ticker']} ({best['score']}) | {worst['ticker']} ({worst['score']}) |")
    p()

    # Top 30 买入 / Top 30 回避
    p("## 🟢 Top 30 长线买入候选")
    p()
    p("| 排名 | 标的 | 板块 | 评分 | 12M | 关键亮点 |")
    p("|------|------|------|------|-----|----------|")
    for idx, r in enumerate(all_sorted[:30], 1):
        sec_short = sector_of.get(r['ticker'], '').split(' (')[0]
        highlights = []
        if r['above_ma200']: highlights.append("MA200上")
        if r['ret_12m'] and r['ret_12m'] > 30: highlights.append(f"12M+{r['ret_12m']:.0f}%")
        if r['rev_growth'] and r['rev_growth'] > 0.2: highlights.append(f"营收+{r['rev_growth']*100:.0f}%")
        if r['profit_margin'] and r['profit_margin'] > 0.2: highlights.append(f"净利率{r['profit_margin']*100:.0f}%")
        if r['roe'] and r['roe'] > 0.2: highlights.append(f"ROE{r['roe']*100:.0f}%")
        if r['peg'] and 0 < r['peg'] < 1.5: highlights.append(f"PEG{r['peg']:.1f}")
        p(f"| {idx} | **{r['ticker']}** | {sec_short} | **{r['score']}** | "
          f"{format_pct(r['ret_12m'],0)} | {', '.join(highlights[:4])} |")
    p()

    p("## 🔴 Top 30 回避 / 高风险列表")
    p()
    p("| 排名 | 标的 | 板块 | 评分 | 12M | 最大回撤 | 波动率 | 关键风险 |")
    p("|------|------|------|------|-----|----------|--------|---------|")
    bottom = all_sorted[-30:][::-1]
    for idx, r in enumerate(bottom, 1):
        sec_short = sector_of.get(r['ticker'], '').split(' (')[0]
        risks = []
        if r['ma200'] and r['price'] < r['ma200']: risks.append("跌破MA200")
        if r['ret_12m'] and r['ret_12m'] < -20: risks.append(f"12M{r['ret_12m']:.0f}%")
        if r['profit_margin'] and r['profit_margin'] < 0: risks.append("亏损")
        if r['max_dd'] and r['max_dd'] < -50: risks.append(f"回撤{r['max_dd']:.0f}%")
        if r['vol_annual'] and r['vol_annual'] > 80: risks.append(f"波动{r['vol_annual']:.0f}%")
        dd_s = f"{r['max_dd']:.0f}%" if r['max_dd'] else "—"
        vol_s = f"{r['vol_annual']:.0f}%" if r['vol_annual'] else "—"
        p(f"| {idx} | **{r['ticker']}** | {sec_short} | **{r['score']}** | "
          f"{format_pct(r['ret_12m'],0)} | {dd_s} | {vol_s} | {', '.join(risks[:3])} |")
    p()

    p("---")
    p(f"*报告生成: {datetime.now().strftime('%Y-%m-%d %H:%M')} · 数据来源: Yahoo Finance*")

    out_path.write_text('\n'.join(lines), encoding='utf-8')
    print(f"\n✅ 报告已保存: {out_path}")


if __name__ == '__main__':
    main()
