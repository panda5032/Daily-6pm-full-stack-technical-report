# Daily 6pm full-stack technical report — cloud routine spec

Routine settings (claude.ai/code/routines → New routine):
- Name: Daily 6pm full-stack technical report
- Schedule: CRON_TZ=America/Chicago 0 18 * * 1-5   (weekdays 6:00pm Central)
- Model: claude-fable-5 · Environment: Claude · Repo: https://github.com/panda5032/Daily-6pm-full-stack-technical-report (main)
- Tools: Bash, Read, Write, Edit, Glob, Grep, WebSearch, Artifact(发布手机报告页,见第 8 节)

## Prompt

你是每个交易日美股盘后（6:00pm 美中时间）的"全栈技术面 + 十六大打法 + 三团队"统一综合分析任务。你现在在 StockInvesting 仓库的一个全新克隆里，全部工作在仓库根目录完成；报告用中文、完整 inline 输出在本会话里；绝不编造数据，缺数据就标"数据缺失"。这是云端运行：没有本地电脑、没有 SendUserFile；图表 HTML 留在沙箱里不提交。

### 0. 准备
1. `pip install -r requirements.txt`
2. 先读 `PLAYBOOKS.md`：打法 1–16、M顶禁买闸、打法12 三修正器（a KOSPI→半导体 / b 恒生→中概闸门 / c BTC→高贝塔温度计）、打法10 R 体系（仓位% = 1% ÷ 止损距离%；总风险 ≤6R，同板块 ≤2R）的权威规则手册，归属与纪律措辞严格沿用。
3. 股票清单来自 `AI_Portfolios.xlsx`（名称→代码映射在 `stock_analysis.py` 的 TICKER_MAP）。已知：SKHY、PEPE-USD 无数据；Gold/Silver/Copper/USO 用 GLD/SLV/CPER/USO 代理。

### 1. 跑引擎（fresh，当天收盘数据）
运行 `bash cloud_daily.sh`。顺序硬约束：先 bollinger_top/bottom（trade_plan_charts 的打法归属读当日 bollinger_*_<日期>.md，缺失会降级并写进 JSON `warnings`），再 stock_analysis / technical_macd_volume_strategy / crypto_derivs（`gauge_12c`）/ market_internals（`regime` + 空头持仓）/ long_term_strategy / earnings_plays，然后 trade_plan_charts.py，最后可选 whale_options_strategy.py（限流失败不致命）。
- 检查每步产出 `<name>_<今日>.md/.json`；yfinance 限流时低并发重试一次，仍失败标"数据缺失"。whale 失败或 NO OPTIONS >20 只（=限流）→ 用仓库里最近一份 whale_options_*.md / whale_deep_dive_*.md 并注明日期。
- JSON `intraday_run: true` 时声明价格为盘中快照、RVOL 为估算值（`rvol_est`）。
- 沙箱无法访问 Yahoo Finance 时如实说明，只输出能产出的部分，不用记忆价格填充。

### 2. 权威数据来源（读文件，不自己重算归属）
- `trade_plans_<今日>.json` plans[ticker]：playbook / playbook_note（归属权威，含 1/2/7/8/9/14/15/16 及 ·12b/·12c/·13死叉闸/·13新金叉/·M顶闸/·深折扣区 后缀）、action / action_plan、entry/entry2/stop/t1/t2、golden_cross/death_cross/cross_age、macd_div14、pin_bar15/pin_low15、mtop_break_days、pb16、deep_disc、knife、bb_pctb/bb_bandwidth/bb_squeeze、patterns、rvol/rvol_est、dist_ma20/50/200、warnings。只在鲸鱼冲突、财报窗口、修正器等特殊情况手动升降级并说明。
- 带轨：bollinger_top_<今日>.md / bollinger_bottom_<今日>.md。
- 大盘风险：market_internals_<今日>.md 的 regime 行；VIX/VIX3M 倒挂、HYG/IEF 20日走阔、池内 MA50 上方 <40%、30Y≥5% 任两项成立 = 全部个股买入信号降一级。
- 12c：crypto_derivs_<今日>.md 的 gauge_12c。
- LT：最新 long_term_strategy_*.json，与上一份比较找单日掉 ≥10 分。
- 财报：最新 earnings_plays_*.md；WebSearch 补两周宏观（非农/CPI/PPI/FOMC）。
- 新金叉/新死叉：今日 plan JSON vs 仓库里前一份 trade_plans_*.json。

### 3. 六大指数 + 三修正器
yfinance 拉 QQQ、SPY、^DJI、^HSI、000001.SS、^KS11（另加 BTC-USD、^VIX）各 2 年日线：收盘 + 1D/5D/20D；MA10/20/50/200 乖离；RSI14；MACD 状态 + 柱 4 日方向；%B、带宽及 6 月分位；ATR14；20/60 日/52 周关键位。给出大盘定调 + 今日主打法（趋势内回调→打法1；squeeze→打法2；破 MA20→只剩打法3）+ 闸门位（QQQ 收破 MA50 = 当日全部买入作废）+ 打法12 三修正器状态行（BTC 结合 gauge_12c）。WebSearch 补一两句当天新闻。

### 4. K 线结构核对
对回调中的强势股（右侧✅/偏右且 5 日下跌）和距 MA20/前突破位 ≤3% 的趋势股拉最近 5 根日 K，逐根实体%/下影%/RVOL，核对五要素（位置/下跌质量/企稳K线三选一/次日确认/大盘闸），标五档：等回调 / 回调中-质量好-等企稳bar / 企稳bar已现-等确认 / 可进场 / 刀-禁接。

### 5. 三团队视角（inline）
技术读图；pattern-team LONG/WAIT/AVOID-EXIT + entry/add/stop/targets；team-analyze PM BUY/HOLD/SELL；research-team（LT+技术）BUY/HOLD/AVOID，异动名字 WebSearch 补新闻。

### 6. 板块 × 打法
按 xlsx 板块逐一给相对强弱（vs QQQ）、内部分化、适用打法（1–16 或全避，应用三修正器）、执行价位、1–3 只重点股。

### 输出结构（全部 inline）
a 六大指数表+定调+主打法+闸门+12修正器行+风险仪表 · b 强弱轮动榜 · c 板块×打法映射 · d 全员汇总表（每只：收盘、右侧、四柱、%B🎯、形态、pattern/PM/research、打法编号、行动）· e Top 5–8 交易计划（打法11 三段式加仓 + 打法10 R 仓位 + 📅财报警示）· e2 组合风险预算 · f 打法1/9 企稳监视名单 · g 打法2 触发单 + 缩量假突破警告（%B>0.85 且 RVOL<0.8）· h 打法4/6 事件日历 + PEAD · i 打法5 鲸鱼交叉 + 空头持仓交叉（🔥逼空燃料/反弹猛非反转/空头环比大增冲突）· j 打法7/8 带轨判定 + 刀名单 + 离场 · j2 ①13新金叉/死叉闸 ②14 ③15(pin_low15) ④M顶闸 ⑤16 pb16 表（双闸 1/2 仓、仅 MA50 闸 1/3 仓、挂 M顶闸只观察）⑥深折扣区（只列当日 14/15 信号中落在 deep_disc 的，为空写"今日无"）· j3 长线四层过滤池 · k 说明 HTML 在沙箱未提交、列出已提交的 JSON/MD · l 一句话操作组合 · m 打法速查表（只列当日引用，注"完整介绍见 PLAYBOOKS.md"）。

成功标准：覆盖全部 ticker；价格为当天收盘；六大指数 + régime + 三修正器完整；每板块和每只有信号的股票有打法编号（来自 plan JSON）；j2 四份名单齐全；j3 齐全；Top 计划有 R 仓位；企稳名单有五要素。

### 7. 持久化
`git add -f` 今日所有 `*_<日期>.json` / `*_<日期>.md`（绝不加 *.html、trade_plan_charts/、_data_cache/）；`git rm` 日期早于 10 天前的 dated 输出；更新 short_interest_cache.json；`git commit -m "daily report <日期>"`；`git push origin main`。推送失败在报告末尾说明。

### 8. 发布手机报告页（Artifact，每天新链接）
inline 报告完成后，把当日报告做成一个手机友好的 HTML 页面并用 Artifact 工具发布为**当天新的 artifact**（不传 `url`，每天独立新链接；私密）：
- `<title>`：`全栈盘后报告 <MM-DD>`（如"全栈盘后报告 10-02"）；icon=`chart`；description 一句话含日期。
- 页面结构沿用 2026-10-01 版（参考会话 artifact Gb8WjKijV5kHyFK2VaLXeU）：顶部 sticky 日期头 + 运行说明框（盘中/收盘、数据缺失如实声明）→ a 六大指数表+定调+闸门+12 修正器 chips+风险仪表 → b 轮动榜 → c 板块×打法 → d 全员汇总表（按板块 `<details>` 折叠，行底色按行动着色）→ e Top 5–8 计划表 + e2 风险预算 → **e3 全员交易计划明细**（trade_plans JSON 全部非回避票，按行动六组折叠：✅/🎯/👀/🟢/⚪/🟠，每票一张卡：现价/入场/加仓/止损/T1/T2/RSI·%B·RVOL + action_plan 原文）→ f–j3 各节 → k/l/m → 新闻来源 + 免责声明。
- 技术要求：浅/深双主题 token（`:root` + `prefers-color-scheme` + `[data-theme]` 三态）；手机 400px 可读、表格包 `overflow-x:auto`；字体 Google Fonts Noto Sans SC + IBM Plex Mono；全部数据来自当日引擎文件，缺失标"缺"。
- 生成方式：用 Python 从 trade_plans/long_term JSON 程序化生成 d 表与 e3 卡片（见 scratchpad 模式：build_report.py / build_plans.py 的做法），避免手写 167 行。
- 发布后把链接写进报告 k 节和 PushNotification 摘要里（通知正文带上 artifact 链接，用户直接从手机点开）。Artifact 工具不可用时跳过此节并在报告中说明。
