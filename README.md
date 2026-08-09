# 🏪 SYT 烟酒店收银系统

> 免费开源 · Python + Tkinter · 适合中小型烟酒店 / 便利店 / 小超市

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.8%2B-blue)](https://python.org)
[![Platform](https://img.shields.io/badge/Platform-Windows%2010%2B-lightgrey)]()

---

## 📸 功能一览

| 模块 | 功能 |
|------|------|
| 🧾 **收银台** | 商品浏览、条码扫码枪、购物车 ±/删除/改数量、**会员选择弹窗**（支持模糊搜索）、**会员价自动切换**、**积分兑换**、现金找零 |
| 📦 **商品管理** | 增删改查、批量类别整理、搜索、操作撤销 |
| 👤 **会员与折扣** | 会员管理、模糊搜索（≥3 位连续匹配）、按商品设置会员价 |
| 📊 **库存管理** | 实时库存、入库/出库、操作日志、撤销 |
| 💰 **销售记录** | 查询 / 明细 / 退货 / 小票弹窗 |
| 📈 **财报分析** | 今日 / 本月 / 本年营收卡片 |
| 💾 **数据备份** | Excel / CSV 导入导出、每日自动备份、数据库重置 |

---

## 🚀 慢速开始（方法一）

### 1. 安装 Python 3.8+

```bash
# 检查版本
python --version   # >= 3.8
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 启动

```bash
python main.py
```

> 💡 首次启动会自动创建 `data/cashier.db` 空数据库。

---

## 📦 打包为 exe

```bash
pip install pyinstaller==5.13.2
pyinstaller SYTCashier.spec
```
打包完成后 `dist/SYTCashier.exe` 即为独立可执行文件，拷贝到任意电脑直接双击运行。

---
## 🚀 快速开始（方法二）
可以直接安装python3.8双击SYTCashier.exe来使用，非常便捷。

## 📁 项目结构

```
SYT/
├── main.py             # Tkinter UI 主程序
├── db.py               # SQLite 数据库层
├── barcode_gun.py      # 扫码枪全局监听
├── SYTCashier.spec     # PyInstaller 打包配置
├── requirements.txt    # Python 依赖
├── .gitignore
├── LICENSE             # MIT 开源协议
└── README.md
```

---

## ⌨️ 扫码枪使用

软件内置扫码枪监听，即插即用：

- 扫码枪自动识别为键盘输入
- 扫描商品条码 → 自动加入购物车
- 无需额外驱动或配置

---

## 🔐 开源协议

MIT License — 可自由使用、修改、分发，包括商业用途。详见 [LICENSE](LICENSE)。

---

## ⚠️ 注意事项

1. **不要将 `data/`、`backups/`、`导出/` 上传到 GitHub**（已通过 `.gitignore` 排除）。
2. 数据库文件 `data/cashier.db` 包含真实交易数据，请妥善保管。
3. 每日自动备份保存在 `backups/daily/` 目录下，建议定期拷贝到 U 盘或云盘。