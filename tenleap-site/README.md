# Tenleap 品牌独立站

Astro 静态站：首页、产品列表、产品详情（数据驱动）、关于、联系、404。

```bash
npm install
npm run dev      # 本地开发 http://localhost:4321
npm run build    # 输出到 dist/，可部署到 Vercel / Netlify / Cloudflare Pages
```

## 改内容只动这几个地方
- `src/data/site.ts`：品牌名、标语、简介、邮箱、社媒链接、导航
- `src/data/products.ts`：产品（名字、价格、状态、卖点、规格）
- `src/pages/index.astro`：首页服务承诺（perks）和技术亮点（tech）
- `src/pages/about.astro`、`src/pages/contact.astro`：品牌故事、FAQ
- `astro.config.mjs`：正式域名

所有占位内容都标了 `TODO`：`grep -rn TODO src astro.config.mjs`。

## 还没接的
- 购买：按钮目前跳到联系页。接 Shopify Buy Button 或 Stripe Payment Link 后替换 `src/pages/products/[slug].astro` 里的链接。
- 订阅：`src/components/Newsletter.astro` 目前不保存邮箱，接 Klaviyo / Mailchimp 后换掉提交逻辑。
- 产品图：目前是 SVG 示意插画（`src/components/ProductArt.astro`），有实拍图后换成 `<img>`。
