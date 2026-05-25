---
name: Selector breakage (AutoDL/Quark UI 改版)
about: kuake init / start / stop / refresh 报 SCRAPER_FAILED
title: "[selector] "
labels: selector-breakage
---

## 失败的命令

```bash
$ kuake <command>
✗ SCRAPER_FAILED
详情: <message>
```

## 报错的 selector 名称

`detail` 字段里通常会指明,如 `autodl_instance_row` / `autodl_power_on` 等。
对应代码位于 [`src/kuake/browser/selectors.py`](../src/kuake/browser/selectors.py)

`<填这里>`

## 当前页面 DOM 截图

附图。

## 相关 DOM 节点(F12 → Elements → 右键 Copy → outerHTML)

```html
<!-- 粘贴这里 -->
```

## 建议的新 selector

如果你已经能定位元素:

```python
# 例如
"[class*='new-instance-class']"
```

## 浏览器 / 平台

- Chrome / Edge / Firefox
- AutoDL/夸克 版本(浏览器右下角往往有 build 号)
- OS
