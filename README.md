# 市场温度计（guore 或自取名字）

三指标切换走势图：巴菲特指数 / A股平均股价 / A股成交额(万亿)。
每交易日 15:50 自动更新（GitHub Actions）。

## 部署（5 分钟）
1. 本仓库 Settings → Pages → Deploy from branch → main / (root) → Save
2. 顶部 Actions → 每日更新市场过热指标 → Run workflow（跑一次初始化）
3. 访问 https://你的用户名.github.io/仓库名
4. 手机浏览器 → 添加到主屏幕

注意：state/ 文件夹里是历史基线数据，勿删。
