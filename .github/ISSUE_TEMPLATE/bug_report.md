---
name: Bug report
about: kuake 报错或行为异常
title: "[bug] "
labels: bug
---

## 现象 / What broke

简述哪个命令、什么时候出错。

## 复现步骤

```bash
$ kuake <command>
# 出错的输出粘贴这里
```

## kuake doctor 输出

```bash
$ kuake doctor
# 完整粘贴
```

## 带 KUAKE_DEBUG 的 traceback

```bash
$ KUAKE_DEBUG=1 kuake <command>
# traceback 完整粘贴
```

## 环境

- OS: (Win 11 / macOS Sonoma / ...)
- Python: `python --version`
- kuake-pipe 版本: `kuake --version`
- 安装方式: `pip install kuake-pipe` / `pip install -e .` / 其他

## 期望行为

应该是什么样的。

## 其他信息

如果是 selector 失效引起的 `SCRAPER_FAILED`,请附:
- 当前 AutoDL/夸克页面截图
- F12 → Elements → 相关元素 outerHTML
