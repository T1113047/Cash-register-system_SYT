# File: C:\code\SYT\main.py
"""烟酒店收银系统 — Tkinter 界面。"""

# ==============================================================================
# 文件结构索引
# ==============================================================================
#   L  21  配置 (BASE_DIR, 数据库与备份目录, 常量, _float 辅助)
#   L  53  CashierApp.__init__ (窗口/Db/扫码枪/类别缓存)
#   L  77  _build_ui (Notebook 7 个 tab 框架)
#   L 110  TreeView 辅助 (_build_tree, _setup_placeholder, _fill_tree, _make_sortable)
#   L 230  收银台 (_build_cashier_tab → 商品列表/购物车/条码搜索/类别筛选)
#   L 440  购物车操作 (_add_to_cart, _refresh_cart, _cart_qty_up/down/set_qty)
#   L 540  会员选择弹窗 (_select_member_dialog, _deactivate_member)
#   L 600  结算 (_checkout → 弹窗: 会员价切换/优惠/实收/确认)
#   L 800  商品管理 (_build_products_tab → 搜索/列表/表单/批量/撤销)
#   L1060  会员与折扣 (_build_members_tab, 编辑/搜索/会员价批量设置)
#   L1250  库存管理 (_build_stock_tab → 库存树/条码定位/日志/撤销/入库/出库)
#   L1430  销售记录 (_build_sales_tab → 查询/明细/退货/小票)
#   L1600  财报分析 (_build_finance_tab → 营收卡片 + 图表数据)
#   L1700  数据备份 (_build_backup_tab → 导入/导出/模板/每日备份/重置)
#   L1800  扫码枪 & 每日备份 & 窗口关闭
# ==============================================================================

import os
import sys
import csv
import json
import queue
import logging
import datetime
import winsound
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Any, Dict, List, Optional, Tuple


from db import Database, DatabaseError

# ------------------------------------------------------------------ #
# 配置
# ------------------------------------------------------------------ #
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "cashier.db")
BACKUP_DIR = os.path.join(BASE_DIR, "backups")
DAILY_BACKUP_DIR = os.path.join(BACKUP_DIR, "daily")
UI_FONT = "Microsoft YaHei"

logging.basicConfig(
    filename=os.path.join(BASE_DIR, "cashier.log"),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("cashier")


def _float_safe(v: str) -> float:
    """安全浮点数，解析失败返回 0。"""
    try:
        return float(v.strip()) if v.strip() else 0.0
    except ValueError:
        return 0.0

def _float(val: str, label: str = "金额") -> float:
    try:
        return round(float(val.strip()), 2)
    except (TypeError, ValueError):
        raise ValueError(f"「{label}」必须是有效数字") from None


# ------------------------------------------------------------------ #
# ToolTip（表格悬停提示）
# ------------------------------------------------------------------ #
class _ToolTip:
    def __init__(self, widget, text=""):
        self.widget = widget
        self.text = text
        self.tw = None
        self.widget.bind("<Enter>", self._enter)
        self.widget.bind("<Leave>", self._leave)

    def _enter(self, _event):
        x = self.widget.winfo_rootx() + 25
        y = self.widget.winfo_rooty() + 25
        self.tw = tk.Toplevel(self.widget)
        self.tw.wm_overrideredirect(True)
        self.tw.wm_geometry(f"+{x}+{y}")
        tk.Label(self.tw, text=self.text, background="#ffffcc", relief="solid", borderwidth=1,
                 font=(UI_FONT, 9)).pack()

    def _leave(self, _event):
        if self.tw:
            self.tw.destroy()
            self.tw = None


# ------------------------------------------------------------------ #
class CashierApp(tk.Tk):
    """收银系统主界面（7 个标签页）。"""

    def __init__(self) -> None:
        super().__init__()
        self.title("烟酒店收银系统")
        self.geometry("1200x750")
        self.minsize(1000, 600)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.db = Database(DB_PATH, BACKUP_DIR)
        self.cart: Dict[int, Any] = {}
        self.active_member: Optional[Dict[str, Any]] = None
        self._barcode_queue: queue.Queue = queue.Queue()
        self._scanner = None

        # 缓存
        self._hover_tooltip: Optional[_ToolTip] = None
        self._category_cache: List[str] = []

        self._build_ui()
        self.after(200, self._refresh_all_first)
        self.after(2000, self._check_daily_backup)
        self.after(80, self._poll_barcode)

    # ------------------------------------------------------------------ #
    # 界面
    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        # 底部状态栏
        self.status_var = tk.StringVar(value="就绪")
        self.status_label = ttk.Label(self, textvariable=self.status_var, relief="sunken", anchor="w",
                                      font=(UI_FONT, 9))
        self.status_label.pack(side="bottom", fill="x")

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True)

        self.tab_cashier = ttk.Frame(self.notebook)
        self.tab_products = ttk.Frame(self.notebook)
        self.tab_members = ttk.Frame(self.notebook)
        self.tab_stock = ttk.Frame(self.notebook)
        self.tab_sales = ttk.Frame(self.notebook)
        self.tab_backup = ttk.Frame(self.notebook)
        self.tab_finance = ttk.Frame(self.notebook)

        self.notebook.add(self.tab_cashier, text="  收银台  ")
        self.notebook.add(self.tab_products, text="  商品管理  ")
        self.notebook.add(self.tab_members, text="  会员与折扣  ")
        self.notebook.add(self.tab_stock, text="  库存管理  ")
        self.notebook.add(self.tab_sales, text="  销售记录  ")
        self.notebook.add(self.tab_backup, text="  数据备份  ")
        self.notebook.add(self.tab_finance, text="  财报分析  ")

        self._build_cashier_tab()
        self._build_products_tab()
        self._build_members_tab()
        self._build_stock_tab()
        self._build_sales_tab()
        self._build_backup_tab()
        self._build_finance_tab()

        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

    # ------------------------------------------------------------------ #
    # TreeView 辅助
    # ------------------------------------------------------------------ #
    def _build_tree(self, parent, columns, height=10):
        col_ids = [c[0] for c in columns]
        tree = ttk.Treeview(parent, columns=col_ids, show="headings", height=height, selectmode="extended")
        for cid, text, width, anchor in columns:
            tree.heading(cid, text=text)
            tree.column(cid, width=width, anchor=anchor, stretch=False)
        return tree

    def _setup_placeholder(self, entry: ttk.Entry, var: tk.StringVar, text: str,
                           color: str = "blue") -> None:
        """为输入框设置占位提示文字。"""
        style_name = f"Placeholder.{color}.TEntry"
        style = ttk.Style()
        style.configure(style_name, foreground=color)
        var.set(text)
        entry.configure(style=style_name)

        def _on_focus_in(e):
            if var.get() == text:
                var.set("")
                entry.configure(style="TEntry")
        def _on_focus_out(e):
            if not var.get().strip():
                var.set(text)
                entry.configure(style=style_name)
        entry.bind("<FocusIn>", _on_focus_in)
        entry.bind("<FocusOut>", _on_focus_out)

    # ------------------------------------------------------------------ #
    # TreeView 辅助
    # ------------------------------------------------------------------ #
    def _fill_tree(self, tree, rows):
        tree.delete(*tree.get_children())
        for values, iid, tag in rows:
            kwargs = {"values": values, "iid": iid}
            if tag:
                kwargs["tags"] = tag
            tree.insert("", "end", **kwargs)

    def _make_sortable(self, tree, numeric_cols, refresh_callback):
        def _sort(col, descending_ref):
            data = []
            for child in tree.get_children(""):
                vals = tree.item(child, "values")
                data.append((vals, child))
            try:
                idx = tree["columns"].index(col)
            except ValueError:
                return
            rev = descending_ref[0]
            numeric = col in numeric_cols
            try:
                data.sort(key=lambda x: (float(x[0][idx]) if x[0][idx] not in ("", "—", None) else 0.0) if numeric else str(x[0][idx]).lower(),
                          reverse=rev)
            except Exception:
                pass
            for item in tree.get_children(""):
                tree.delete(item)
            for vals, iid in data:
                tree.insert("", "end", values=vals, iid=iid)
            descending_ref[0] = not rev

        desc = [False]
        for col in tree["columns"]:
            tree.heading(col, command=lambda c=col, d=desc: _sort(c, d))

    # ------------------------------------------------------------------ #
    # 收银台
    # ------------------------------------------------------------------ #
    def _build_cashier_tab(self) -> None:
        top = ttk.Frame(self.tab_cashier)
        top.pack(fill="x", padx=8, pady=(4, 0))

        # 会员激活区
        member_frame = ttk.LabelFrame(top, text="会员", padding=4)
        member_frame.pack(side="left", fill="x", padx=(0, 6))
        ttk.Button(member_frame, text="选择会员", command=self._select_member_dialog, width=10).pack(side="left", padx=2)
        ttk.Button(member_frame, text="取消", command=self._deactivate_member, width=5).pack(side="left", padx=2)
        self.member_status_var = tk.StringVar(value="未激活（按原价销售）")
        ttk.Label(member_frame, textvariable=self.member_status_var, foreground="gray",
                  font=(UI_FONT, 9)).pack(side="left", padx=(6, 2))

        # 类别筛选
        cat_frame = ttk.LabelFrame(top, text="商品类别", padding=4)
        cat_frame.pack(side="left", fill="x")
        self.cashier_cat_var = tk.StringVar(value="全部分类")
        self.cashier_cat_combo = ttk.Combobox(cat_frame, textvariable=self.cashier_cat_var,
                                              state="readonly", width=14, font=(UI_FONT, 10))
        self.cashier_cat_combo.pack(side="left", padx=2)
        self.cashier_cat_combo.bind("<<ComboboxSelected>>", lambda _: self._refresh_product_list())
        ttk.Button(cat_frame, text="刷新", command=self._refresh_product_list, width=5).pack(side="left", padx=4)

        # 搜索 / 条码输入
        search_frame = ttk.Frame(top)
        search_frame.pack(side="right")
        self.cashier_search_var = tk.StringVar()
        self._cashier_search_suppress = False
        self.cashier_search_var.trace_add("write", lambda *_: self._refresh_product_list())
        self.cashier_search_entry = ttk.Entry(search_frame, textvariable=self.cashier_search_var, width=28,
                                              font=(UI_FONT, 12))
        self.cashier_search_entry.pack(side="left")
        self.cashier_search_entry.bind("<Escape>", self._defocus_search)
        self._setup_placeholder(self.cashier_search_entry, self.cashier_search_var, "输入名称或条码")
        # 覆盖 FocusOut：收银台搜索框恢复占位时不触发商品列表刷新
        self.cashier_search_entry.unbind("<FocusOut>")
        def _cashier_focus_out(e):
            if not self.cashier_search_var.get().strip():
                self._cashier_search_suppress = True
                self.cashier_search_var.set("输入名称或条码")
                self._cashier_search_suppress = False
                self.cashier_search_entry.configure(style="Placeholder.blue.TEntry")
        self.cashier_search_entry.bind("<FocusOut>", _cashier_focus_out)
        def _cashier_barcode_search():
            q = self.cashier_search_var.get().strip()
            if not q or q == "可输入条码":
                return
            results = self._fuzzy_barcode_search(q)
            if not results:
                self._set_status(f"未找到条码: {q}", "red")
            elif len(results) == 1 and results[0][0] == 1.0:
                self._add_to_cart(results[0][1])
                self._set_status(f"找到: {results[0][1]['name']}", "green")
            else:
                self._show_barcode_search_popup(
                    q, results,
                    lambda p: (self._add_to_cart(p), self._set_status(f"找到: {p['name']}", "green"))
                )
        ttk.Button(search_frame, text="搜索", command=_cashier_barcode_search, width=5).pack(side="left", padx=(2, 0))
        ttk.Label(search_frame, text="🔍", font=(UI_FONT, 10)).pack(side="left", padx=(2, 4))

        # 商品列表 + 购物车
        body = ttk.Frame(self.tab_cashier)
        body.pack(fill="both", expand=True, padx=8, pady=6)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)

        # 商品列表
        left = ttk.LabelFrame(body, text="商品列表", padding=4)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        self.product_tree = self._build_tree(
            left, (("id", "ID", 40, "center"), ("name", "商品名称", 200, "w"),
                   ("category", "类别", 70, "center"), ("price", "售价", 60, "e"),
                   ("mprice", "会员价", 60, "e"), ("stock", "库存", 45, "e")),
            height=16)
        self.product_tree.pack(fill="both", expand=True)
        self._make_sortable(self.product_tree, {"id", "price", "mprice", "stock"}, self._refresh_product_list)
        # 双击添加
        self.product_tree.bind("<Double-1>", lambda _: self._from_list_add_to_cart())
        # 单击名称 → 超链接预览
        self.product_tree.bind("<Double-1>", self._on_product_name_click)

        # 购物车
        right = ttk.LabelFrame(body, text="购物车", padding=4)
        right.grid(row=0, column=1, sticky="nsew")
        self.cart_tree = self._build_tree(
            right, (("name", "商品", 125, "w"), ("price", "单价", 55, "e"),
                    ("qty", "数量", 40, "center"), ("subtotal", "小计", 65, "e")),
            height=10)
        self.cart_tree.pack(fill="both", expand=True)
        cart_btns = ttk.Frame(right)
        cart_btns.pack(fill="x", pady=(4, 0))
        ttk.Button(cart_btns, text="+", command=self._cart_qty_up, width=4).pack(side="left", padx=1)
        ttk.Button(cart_btns, text="-", command=self._cart_qty_down, width=4).pack(side="left", padx=1)
        self.cart_qty_var = tk.StringVar()
        cart_qty_entry = ttk.Entry(cart_btns, textvariable=self.cart_qty_var, width=5,
                                   font=(UI_FONT, 10), justify="center")
        cart_qty_entry.pack(side="left", padx=2)
        cart_qty_entry.bind("<Return>", self._cart_set_qty)
        self._setup_placeholder(cart_qty_entry, self.cart_qty_var, "数量", "black")
        ttk.Button(cart_btns, text="确认", command=self._cart_set_qty, width=5).pack(side="left", padx=1)
        ttk.Button(cart_btns, text="删除", command=self._cart_remove, width=5).pack(side="left", padx=1)
        ttk.Button(cart_btns, text="清空", command=self._cart_clear, width=5).pack(side="left", padx=1)

        self.cart_total_var = tk.StringVar(value="合计: ¥0.00")
        ttk.Label(right, textvariable=self.cart_total_var, font=(UI_FONT, 16, "bold"),
                  foreground="#d33").pack(anchor="e", pady=(8, 0))
        ttk.Button(right, text="结算 (Enter)", command=self._checkout, width=20).pack(fill="x", pady=(6, 0))
        self.bind("<Return>", lambda _: self._checkout())

    def _refresh_category_combos(self) -> None:
        """从全量商品同步收银、表单和批量类别候选。"""
        try:
            categories = self.db.get_product_categories()
        except Exception:
            logger.exception("读取全部商品类别失败")
            categories = ["其他"]

        self._category_cache = ["全部分类"] + categories
        self.cashier_cat_combo["values"] = self._category_cache
        if hasattr(self, "prod_batch_category_combo"):
            self.prod_batch_category_combo["values"] = categories
        if hasattr(self, "prod_form_category_combo"):
            self.prod_form_category_combo["values"] = categories

    def _refresh_category_combo(self) -> None:
        """兼容既有调用，刷新全部类别候选。"""
        self._refresh_category_combos()
    # 商品名称双击 → 加入购物车并选中
    def _on_product_name_click(self, event: tk.Event) -> None:
        region = self.product_tree.identify("region", event.x, event.y)
        column = self.product_tree.identify("column", event.x, event.y)
        item = self.product_tree.identify_row(event.y)
        if region != "cell" or column != "#2" or not item:
            return
        vals = self.product_tree.item(item, "values")
        if not vals:
            return
        pid = int(vals[0])
        try:
            p = self.db.get_product(pid)
        except Exception:
            return
        if p is None:
            return
        self._add_to_cart(p)
        iid = str(pid)
        if self.cart_tree.exists(iid):
            self.cart_tree.selection_set(iid)
            self.cart_tree.focus(iid)
            self.cart_tree.see(iid)
    def _refresh_product_list(self) -> None:
        if getattr(self, "_cashier_search_suppress", False):
            return
        keyword = self.cashier_search_var.get()
        if keyword in ("可输入条码", "输入名称或条码"):
            keyword = ""
        try:
            products = self.db.search_products(keyword)
        except Exception:
            logger.exception("查询商品失败")
            return
        cat_filter = self.cashier_cat_var.get()
        if cat_filter and cat_filter != "全部分类":
            products = [p for p in products if (p.get("category") or "其他") == cat_filter]
        self._refresh_category_combo()
        rows = []
        for p in products:
            mp = p.get("member_price")
            tag = ("low",) if p["stock"] <= p["low_stock"] else ()
            rows.append(((p["id"], p["name"], p.get("category", ""),
                          f"{p['sell_price']:.2f}",
                          f"{mp:.2f}" if mp else "—",
                          p["stock"]), str(p["id"]), tag))
        self._fill_tree(self.product_tree, rows)
        self.product_tree.tag_configure("low", foreground="red")

    def _defocus_search(self, _event=None) -> None:
        """Escape 键清空搜索框并释放焦点。"""
        self.cashier_search_var.set("")
        self.cashier_search_entry.selection_clear()
        self.focus()

    def _focus_search(self) -> None:
        """自动聚焦到条码/搜索输入框。"""
        self.cashier_search_entry.focus_set()

    def _from_list_add_to_cart(self) -> None:
        sel = self.product_tree.selection()
        if not sel:
            return
        try:
            p = self.db.get_product(int(sel[0]))
        except Exception:
            return
        if p is None:
            return
        self._add_to_cart(p)

    def _add_to_cart(self, p: Dict[str, Any]) -> None:
        pid = int(p["id"])
        mp = p.get("member_price")
        base_price = p["sell_price"]
        is_member = self.active_member is not None
        if is_member and mp:
            price = mp
        else:
            price = base_price
        if pid in self.cart:
            if self.cart[pid]["qty"] >= p["stock"]:
                messagebox.showwarning("库存不足", f"「{p['name']}」库存仅 {p['stock']}")
                return
            self.cart[pid]["qty"] += 1
        else:
            if p["stock"] <= 0:
                messagebox.showwarning("库存不足", f"「{p['name']}」已售罄")
                return
            self.cart[pid] = {
                "id": pid, "name": p["name"], "base_price": base_price,
                "price": price, "member_price": mp, "qty": 1,
                "product_id": pid, "product_name": p["name"],
            }
        self._refresh_cart()

    def _refresh_cart(self) -> None:
        sel_before = self.cart_tree.selection()
        self.cart_tree.delete(*self.cart_tree.get_children())
        total = 0.0
        for pid, item in self.cart.items():
            st = item["price"] * item["qty"]
            total += st
            self.cart_tree.insert("", "end", iid=str(pid),
                                  values=(item["name"], f"{item['price']:.2f}",
                                          item["qty"], f"{st:.2f}"))
        self.cart_total_var.set(f"合计: ¥{total:.2f}")
        for iid in sel_before:
            if self.cart_tree.exists(iid):
                self.cart_tree.selection_add(iid)
                self.cart_tree.focus(iid)

    def _cart_step(self) -> int:
        """读取数量输入框的值作为步长，默认 1。"""
        try:
            return int(self.cart_qty_var.get().strip())
        except ValueError:
            return 1

    def _cart_qty_up(self) -> None:
        sel = self.cart_tree.selection()
        if not sel:
            return
        pid = int(sel[0])
        step = self._cart_step()
        try:
            p = self.db.get_product(self.cart[pid]["product_id"])
        except Exception:
            return
        if p and self.cart[pid]["qty"] + step > p["stock"]:
            messagebox.showwarning("库存不足", f"「{p['name']}」库存仅 {p['stock']}")
            return
        self.cart[pid]["qty"] += step
        self._refresh_cart()

    def _cart_qty_down(self) -> None:
        sel = self.cart_tree.selection()
        if not sel:
            return
        pid = int(sel[0])
        step = self._cart_step()
        self.cart[pid]["qty"] -= step
        if self.cart[pid]["qty"] <= 0:
            del self.cart[pid]
        self._refresh_cart()

    def _cart_remove(self) -> None:
        sel = self.cart_tree.selection()
        if not sel:
            return
        pid = int(sel[0])
        if pid in self.cart:
            del self.cart[pid]
        self._refresh_cart()

    def _cart_set_qty(self, _event=None) -> None:
        val = self.cart_qty_var.get().strip()
        if not val or val == "数量":
            return
        try:
            qty = int(val)
        except ValueError:
            messagebox.showerror("输入错误", "请输入整数")
            return
        if qty == 0:
            return
        sel = self.cart_tree.selection()
        if not sel:
            messagebox.showwarning("未选中", "请先在购物车中选中一个商品")
            return
        pid = int(sel[0])
        try:
            p = self.db.get_product(self.cart[pid]["product_id"])
        except Exception:
            return
        new_qty = qty
        if new_qty <= 0:
            del self.cart[pid]
            self._refresh_cart()
            return
        if p and new_qty > p["stock"]:
            messagebox.showwarning("库存不足", f"「{p['name']}」库存仅 {p['stock']}")
            return
        self.cart[pid]["qty"] = new_qty
        self._refresh_cart()

    def _cart_clear(self) -> None:
        self.cart.clear()
        self._refresh_cart()

    # ------------------------------------------------------------------ #
    # 收银台 — 会员激活
    # ------------------------------------------------------------------ #
    def _select_member_dialog(self) -> None:
        """弹出会员选择二级窗口，支持搜索 + 列表双击选取。"""
        win = tk.Toplevel(self)
        win.title("选择会员")
        win.geometry("420x400")
        win.transient(self)
        win.grab_set()

        # 搜索行
        sf = ttk.Frame(win, padding=6)
        sf.pack(fill="x")
        search_var = tk.StringVar()
        ttk.Entry(sf, textvariable=search_var, font=(UI_FONT, 11)).pack(side="left", fill="x", expand=True)
        ttk.Label(sf, text="≥3位模糊", foreground="gray", font=(UI_FONT, 8)).pack(side="left", padx=(4, 0))

        # 会员列表
        tree = self._build_tree(
            win,
            (("phone", "手机号", 105, "center"), ("name", "姓名", 80, "w"),
             ("points", "积分", 55, "center"), ("created", "注册", 110, "center")),
        )
        tree.configure(selectmode="browse")
        tree.pack(fill="both", expand=True, padx=6, pady=4)

        def _do_search(*_):
            kw = search_var.get().strip()
            try:
                members = self.db.search_members_fuzzy(kw)
            except Exception:
                members = []
            rows = [((m["phone"], m.get("name") or "", m.get("points", 0),
                     (m.get("created_at") or "")[:10]), str(m["id"]), ()) for m in members]
            self._fill_tree(tree, rows)

        search_var.trace_add("write", _do_search)
        _do_search()

        def _on_select(_event=None):
            sel = tree.selection()
            if not sel:
                return
            vals = tree.item(sel[0], "values")
            if vals:
                member_id = int(sel[0])  # iid 即为 member id
                try:
                    member = self.db.get_member(member_id)
                except Exception:
                    return
                if member:
                    self.active_member = member
                    self.member_status_var.set(f"已激活: {self._member_display(member)} — 会员价生效")
                    self._refresh_cart()
                    self._set_status(f"会员 {self._member_display(member)} 已激活", "green")
            win.destroy()

        tree.bind("<Double-1>", _on_select)
        win.bind("<Return>", _on_select)

        btn_row = ttk.Frame(win, padding=6)
        btn_row.pack(fill="x")
        ttk.Button(btn_row, text="确认选择", command=_on_select, width=15).pack(side="right")
        ttk.Button(btn_row, text="取消", command=win.destroy, width=8).pack(side="right", padx=4)

        win.wait_window()

    def _deactivate_member(self) -> None:
        self.active_member = None
        self.member_status_var.set("未激活（按原价销售）")
        self._refresh_cart()
        self._set_status("已取消会员价，恢复原价", "green")

    @staticmethod
    def _member_display(member: Dict[str, Any]) -> str:
        name = (member.get("name") or "").strip()
        phone = member["phone"]
        pts = member.get("points", 0)
        if name:
            return f"{name}（{phone}）[积分:{pts}]"
        return f"{phone} [积分:{pts}]"

    # ------------------------------------------------------------------ #
    # 结算
    # ------------------------------------------------------------------ #
    def _update_checkout_pts(self) -> None:
        """刷新结算窗口的积分显示。"""
        if self.active_member is None or not hasattr(self, "_checkout_current_total"):
            return
        m = self.db.get_member(self.active_member["id"])
        if m:
            self._checkout_pts_label.config(text=f"当前积分: {m.get('points', 0)}")
        # 计算即将获得的积分（非烟类）
        total = self._checkout_current_total
        discount = _float_safe(self._discount_var.get())
        non_tobacco = 0.0
        for it in self.cart.values():
            try:
                p = self.db.get_product(it["product_id"])
                if p and p.get("category") != "烟":
                    non_tobacco += self._cart_price(it) * it["qty"]
            except Exception:
                pass
        if non_tobacco > 0 and total > 0 and not self._checkout_exchange_var.get():
            pts = int((non_tobacco / total) * (total - discount))
            self._checkout_pts_earn_label.config(text=f"本次可获积分: +{pts}")
        else:
            self._checkout_pts_earn_label.config(text="本次可获积分: 0")

    def _toggle_exchange(self) -> None:
        """切换积分兑换模式：禁用/启用实收和优惠字段，联动数值。"""
        enabled = not self._checkout_exchange_var.get()
        state = "normal" if enabled else "disabled"
        for w in (self._discount_entry, self._paid_entry):
            w.configure(state=state)
        if not enabled:
            self._discount_var.set(f"{self._checkout_current_total:.2f}")
            self._paid_var.set("0.00")
        self._recalc_checkout()
        self._update_checkout_pts()

    def _checkout(self) -> None:
        if not self.cart:
            messagebox.showwarning("提示", "购物车为空，无法结算")
            return
        is_member = self.active_member is not None
        base_total = round(sum(float(i["base_price"]) * i["qty"] for i in self.cart.values()), 2)
        total = round(sum(self._cart_price(i) * i["qty"] for i in self.cart.values()), 2)
        save = round(base_total - total, 2)
        ratio = (save / base_total * 100) if base_total > 0 else 0.0

        win = tk.Toplevel(self)
        win.title("结算" + (f" - 会员 {self._member_display(self.active_member)}" if is_member else ""))
        win.transient(self)
        win.grab_set()
        win.resizable(False, False)
        win.minsize(520, 420)

        FONT = (UI_FONT, 13)
        FONT_BOLD = (UI_FONT, 13, "bold")
        FONT_TOTAL = (UI_FONT, 22, "bold")

        box = ttk.Frame(win, padding=20)
        box.pack(fill="both", expand=True)

        # 会员价切换 — 始终可用
        ctrl = ttk.Frame(box)
        ctrl.pack(fill="x", pady=(0, 6))
        if is_member:
            ttk.Label(ctrl, text=f"会员: {self._member_display(self.active_member)} 已激活",
                      foreground="#d33", font=FONT_BOLD).pack(side="left")
        else:
            has_mp = any(i.get("member_price") for i in self.cart.values())
            ttk.Label(ctrl, text="非会员模式" if not has_mp else "非会员（有会员价商品）",
                      foreground="#555", font=FONT_BOLD).pack(side="left")
        self._checkout_use_member = tk.BooleanVar(value=is_member)
        ttk.Checkbutton(ctrl, text="使用会员价", variable=self._checkout_use_member,
                        command=self._recalc_checkout).pack(side="right")

        # 明细
        self._checkout_detail = ttk.Treeview(
            box, columns=("name", "base", "mprice", "qty", "subtotal"), show="headings",
            height=min(max(len(self.cart), 1), 8))
        for cid, text, width, anchor in [
            ("name", "商品", 180, "w"), ("base", "原价", 70, "e"),
            ("mprice", "会员价", 70, "e"), ("qty", "数量", 50, "center"),
            ("subtotal", "小计", 90, "e"),
        ]:
            self._checkout_detail.heading(cid, text=text)
            self._checkout_detail.column(cid, width=width, anchor=anchor)
        self._checkout_detail.pack(fill="x", pady=(0, 8))

        self._checkout_total_label = ttk.Label(box, text="", font=FONT_TOTAL, foreground="#d33")
        self._checkout_total_label.pack(anchor="e")
        self._checkout_save_label = ttk.Label(box, text="", font=FONT_BOLD, foreground="#d33")
        self._checkout_save_label.pack(anchor="e")

        # 会员积分信息 + 积分兑换
        self._checkout_pts_frame = ttk.Frame(box)
        self._checkout_pts_label = ttk.Label(self._checkout_pts_frame, text="", font=(UI_FONT, 12), foreground="#06c")
        self._checkout_pts_earn_label = ttk.Label(self._checkout_pts_frame, text="", font=(UI_FONT, 11), foreground="#090")

        self._checkout_exchange_var = tk.BooleanVar(value=False)
        self._checkout_exchange_cb = ttk.Checkbutton(
            self._checkout_pts_frame, text="积分兑换", variable=self._checkout_exchange_var,
            command=self._toggle_exchange)
        self._checkout_exchange_entry = ttk.Entry(self._checkout_pts_frame, width=10)
        self._checkout_exchange_entry.insert(0, "0")

        if is_member:
            self._checkout_pts_frame.pack(fill="x", pady=(6, 0))
            self._checkout_pts_label.pack(anchor="w")
            self._checkout_pts_earn_label.pack(anchor="w")
            self._checkout_exchange_cb.pack(side="left", pady=(4, 0))
            self._checkout_exchange_entry.pack(side="left", padx=6, pady=(4, 0))
            ttk.Label(self._checkout_pts_frame, text="分", font=(UI_FONT, 11)).pack(side="left", pady=(4, 0))
            self._update_checkout_pts()

        ttk.Separator(box).pack(fill="x", pady=12)
        ttk.Label(box, text="手动优惠金额（可选）:", font=FONT).pack(anchor="w")
        self._discount_var = tk.StringVar(value="0")
        self._discount_entry = ttk.Entry(box, textvariable=self._discount_var, width=18, font=FONT)
        self._discount_entry.pack(fill="x", pady=(4, 8))
        ttk.Label(box, text="实收金额:", font=FONT).pack(anchor="w")
        self._paid_var = tk.StringVar(value=f"{total:.2f}")
        self._paid_entry = ttk.Entry(box, textvariable=self._paid_var, width=18, font=FONT)
        self._paid_entry.pack(fill="x", pady=(4, 8))

        def _recalc():
            self._recalc_checkout()

        self._checkout_win = win
        self._recalc_checkout()

        def confirm():
            exchange_mode = self._checkout_exchange_var.get() and is_member
            if exchange_mode:
                try:
                    exchange_pts = int(self._checkout_exchange_entry.get().strip())
                except ValueError:
                    messagebox.showerror("输入错误", "兑换积分必须为整数", parent=win)
                    return
                if exchange_pts <= 0:
                    messagebox.showerror("输入错误", "兑换积分必须大于 0", parent=win)
                    return
                m = self.db.get_member(self.active_member["id"])
                if m and m.get("points", 0) < exchange_pts:
                    messagebox.showerror("积分不足",
                                         f"当前积分 {m['points']}，需要 {exchange_pts}", parent=win)
                    return
                discount = self._checkout_current_total
                paid = 0.0
            else:
                try:
                    discount = _float(self._discount_var.get(), "优惠金额")
                    paid = _float(self._paid_var.get(), "实收金额")
                except ValueError as exc:
                    messagebox.showerror("输入错误", str(exc), parent=win)
                    return
            current_total = self._checkout_current_total
            due = current_total - discount
            if due < 0:
                messagebox.showerror("输入错误", "优惠金额不能超过应收金额", parent=win)
                return
            if not exchange_mode and paid < due:
                messagebox.showerror("输入错误", "实收金额不足", parent=win)
                return
            items = [{
                "product_id": i["product_id"], "product_name": i["name"],
                "price": i["price"], "quantity": i["qty"],
            } for i in self.cart.values()]
            try:
                member_id = self.active_member["id"] if self.active_member else None
                if exchange_mode:
                    # 积分兑换：全额优惠，不付钱，不积分
                    sale_id, order_no, change, _ = self.db.create_sale(
                        items, discount=discount, paid_amount=0.0, member_id=member_id,
                    )
                    self.db.adjust_member_points(member_id, -exchange_pts, f"兑换 {exchange_pts} 分")
                    points_earned = 0
                else:
                    sale_id, order_no, change, points_earned = self.db.create_sale(
                        items, discount=discount, paid_amount=paid, member_id=member_id,
                    )
            except DatabaseError as exc:
                messagebox.showerror("结算失败", str(exc), parent=win)
                return
            except Exception:
                logger.exception("结算异常")
                messagebox.showerror("结算失败", "发生未知错误", parent=win)
                return
            msg = f"销售单 {order_no} 已完成"
            if exchange_mode:
                msg += f"\n\n积分兑换 — 扣除 {exchange_pts} 分\n商品已送出"
            else:
                msg += f"\n\n应收: ¥{due:.2f}\n实收: ¥{paid:.2f}\n找零: ¥{change:.2f}"
            if is_member:
                msg += f"\n\n会员: {self._member_display(self.active_member)}"
                if not exchange_mode:
                    msg += f"\n会员优惠: ¥{save:.2f}（{ratio:.1f}%）"
                if points_earned:
                    msg += f"\n本次积分: +{points_earned}"
            messagebox.showinfo("结算成功", msg, parent=win)
            win.destroy()
            self.cart.clear()
            self._refresh_cart()
            self._refresh_product_list()
            self._refresh_products_tab()
            self._refresh_stock_tab()
            self._refresh_members_tab()
            self._refresh_finance_tab()
            if self.active_member:
                self.active_member = None
                self.member_status_var.set("未激活（按原价销售）")
                self._set_status("已退出当前会员", "gray")

        ttk.Button(box, text="确认收款", command=confirm, width=24).pack(pady=(14, 4))
        win.bind("<Return>", lambda _: confirm())

    # 结算工具
    def _cart_price(self, item: Dict[str, Any]) -> float:
        mp = item.get("member_price")
        if mp and hasattr(self, "_checkout_use_member") and self._checkout_use_member.get():
            return mp
        return item["base_price"]

    def _recalc_checkout(self) -> None:
        use_member = (hasattr(self, "_checkout_use_member") and self._checkout_use_member.get())
        base_total = round(sum(float(i["base_price"]) * i["qty"] for i in self.cart.values()), 2)

        # 重新计算每个商品的当前价格
        for i in self.cart.values():
            if use_member and i.get("member_price"):
                i["price"] = i["member_price"]
            else:
                i["price"] = i["base_price"]

        total = round(sum(i["price"] * i["qty"] for i in self.cart.values()), 2)
        save = round(base_total - total, 2)
        ratio = (save / base_total * 100) if base_total > 0 else 0.0
        self._checkout_current_total = total

        # 刷新明细
        self._checkout_detail.delete(*self._checkout_detail.get_children())
        for item in self.cart.values():
            mp = item.get("member_price")
            self._checkout_detail.insert("", "end", values=(
                item["name"], f"{item['base_price']:.2f}",
                f"{mp:.2f}" if mp else "—",
                item["qty"], f"{item['price'] * item['qty']:.2f}",
            ))

        if use_member:
            self._checkout_total_label.config(text=f"会员价合计(应收): ¥{total:.2f}")
            self._checkout_save_label.config(text=f"优惠: ¥{save:.2f}（{ratio:.1f}%）")
        else:
            self._checkout_total_label.config(text=f"应收合计: ¥{total:.2f}")
            self._checkout_save_label.config(text="")

        self._paid_var.set(f"{total:.2f}")
        self._update_checkout_pts()

    # ------------------------------------------------------------------ #
    # 商品管理
    # ------------------------------------------------------------------ #
    def _build_products_tab(self) -> None:
        top = ttk.Frame(self.tab_products)
        top.pack(fill="both", expand=True)

        self.prod_search_var = tk.StringVar()
        self.prod_search_var.trace_add("write", lambda *_: self._refresh_products_tab())
        srow = ttk.Frame(top)
        srow.pack(fill="x", padx=8, pady=(8, 4))
        ttk.Entry(srow, textvariable=self.prod_search_var).pack(side="left", fill="x", expand=True)
        ttk.Button(srow, text="刷新", command=self._refresh_products_tab, width=6).pack(side="left", padx=(4, 0))
        ttk.Label(srow, text="支持 Ctrl/Shift 多选", foreground="gray").pack(side="left", padx=(10, 0))

        tree_frame = ttk.Frame(top)
        tree_frame.pack(fill="both", expand=True, padx=8)
        self.prod_tree = self._build_tree(
            tree_frame, (("id", "ID", 45, "center"), ("barcode", "条码", 110, "center"),
                  ("name", "名称", 160, "w"), ("category", "类别", 65, "center"),
                  ("cost", "进价", 55, "e"), ("sell", "售价", 55, "e"),
                  ("mp", "会员价", 55, "e"), ("stock", "库存", 45, "e"),
                  ("low", "预警", 45, "e"), ("created", "创建时间", 110, "center")),
            height=10)
        self.prod_tree.pack(fill="both", expand=True)
        self._make_sortable(self.prod_tree, {"id", "cost", "sell", "mp", "stock", "low"}, self._refresh_products_tab)
        self.prod_tree.tag_configure("low", foreground="red")
        self.prod_tree.bind("<<TreeviewSelect>>", self._on_product_select)

        pform = ttk.LabelFrame(top, text="编辑商品（单击列表行填充）", padding=8)
        pform.pack(fill="x", padx=8, pady=(6, 8))
        self.prod_form_vars: Dict[str, tk.Variable] = {
            "id": tk.StringVar(), "barcode": tk.StringVar(), "name": tk.StringVar(),
            "category": tk.StringVar(value="其他"), "cost": tk.StringVar(),
            "sell": tk.StringVar(), "mp": tk.StringVar(), "stock": tk.StringVar(),
            "low": tk.StringVar(value="10"),
        }
        row1 = ttk.Frame(pform)
        row1.pack(fill="x", pady=2)
        for text, key, w in [("条码", "barcode", 14), ("名称*", "name", 18), ("类别", "category", 8)]:
            ttk.Label(row1, text=text).pack(side="left", padx=(8, 2))
            if key == "category":
                self.prod_form_category_combo = ttk.Combobox(
                    row1, textvariable=self.prod_form_vars[key], state="normal", width=w
                )
                ent = self.prod_form_category_combo
            else:
                ent = ttk.Entry(row1, textvariable=self.prod_form_vars[key], width=w)
            ent.pack(side="left")
            if key == "barcode":
                self._setup_placeholder(ent, self.prod_form_vars["barcode"], "可输入条码")
                def _prod_barcode_search():
                    q = self.prod_form_vars["barcode"].get().strip()
                    if not q or q == "可输入条码":
                        return
                    results = self._fuzzy_barcode_search(q)
                    if not results:
                        self._set_status(f"未找到条码: {q}", "red")
                    elif len(results) == 1 and results[0][0] == 1.0:
                        self._fill_product_form(results[0][1])
                        self._refresh_products_tab()
                    else:
                        self._show_barcode_search_popup(
                            q, results,
                            lambda p: (self._fill_product_form(p), self._refresh_products_tab())
                        )
                ttk.Button(row1, text="搜索", command=_prod_barcode_search, width=5).pack(side="left", padx=2)
        row2 = ttk.Frame(pform)
        row2.pack(fill="x", pady=2)
        for text, key, w in [("进价", "cost", 7), ("售价", "sell", 7), ("会员价", "mp", 7),
                              ("库存", "stock", 6), ("预警线", "low", 5)]:
            ttk.Label(row2, text=text).pack(side="left", padx=(8, 2))
            ttk.Entry(row2, textvariable=self.prod_form_vars[key], width=w).pack(side="left")
        btns = ttk.Frame(pform)
        btns.pack(fill="x", pady=(6, 0))
        ttk.Button(btns, text="新增商品", command=self._add_product).pack(side="left", padx=4)
        ttk.Button(btns, text="保存修改", command=self._update_product).pack(side="left", padx=4)
        ttk.Button(btns, text="删除商品", command=self._delete_product).pack(side="left", padx=4)
        ttk.Button(btns, text="清空表单", command=self._clear_product_form).pack(side="left", padx=4)

        batch_row = ttk.LabelFrame(top, text="批量整理商品种类", padding=6)
        batch_row.pack(fill="x", padx=8, pady=(0, 8))
        self.prod_batch_category_var = tk.StringVar()
        ttk.Label(batch_row, text="目标类别：").pack(side="left")
        self.prod_batch_category_combo = ttk.Combobox(
            batch_row, textvariable=self.prod_batch_category_var, state="normal", width=18
        )
        self.prod_batch_category_combo.pack(side="left", padx=(0, 6))
        ttk.Button(
            batch_row, text="批量修改类别", command=self._batch_update_product_category
        ).pack(side="left", padx=4)
        ttk.Button(
            batch_row, text="批量删除所选商品", command=self._batch_delete_products
        ).pack(side="left", padx=4)
        ttk.Button(
            batch_row, text="撤回上一次商品操作", command=self._undo_last_product_operation
        ).pack(side="left", padx=4)

    def _refresh_products_tab(self) -> None:
        try:
            products = self.db.search_products(self.prod_search_var.get())
        except Exception:
            logger.exception("查询商品失败")
            return
        rows = []
        for p in products:
            mp = p.get("member_price")
            tag = ("low",) if p["stock"] <= p["low_stock"] else ()
            rows.append(((p["id"], p["barcode"] or "", p["name"], p["category"],
                          f"{p['cost_price']:.2f}", f"{p['sell_price']:.2f}",
                          f"{mp:.2f}" if mp else "—", p["stock"], p["low_stock"],
                          p["created_at"]), str(p["id"]), tag))
        selected = set(self.prod_tree.selection())
        self._fill_tree(self.prod_tree, rows)
        self.prod_tree.tag_configure("low", foreground="red")
        for iid in selected:
            if self.prod_tree.exists(iid):
                self.prod_tree.selection_add(iid)
        self._refresh_category_combos()

    def _refresh_product_related_views(self) -> None:
        """刷新商品管理、收银台、库存和相关类别数据。"""
        self._refresh_products_tab()
        self._refresh_product_list()
        self._refresh_stock_tab()
        self._refresh_members_tab()

    def _batch_update_product_category(self) -> None:
        """确认后批量更新商品管理列表中所选商品的类别。"""
        selected = self.prod_tree.selection()
        category = self.prod_batch_category_var.get().strip()
        if not selected:
            messagebox.showwarning("未选择", "请使用 Ctrl/Shift 在商品列表中多选商品")
            return
        if not category:
            messagebox.showwarning("类别为空", "请选择或输入目标类别")
            return
        if not messagebox.askyesno(
            "确认批量修改",
            "确定将所选 %d 个商品的类别统一修改为「%s」吗？" % (len(selected), category),
        ):
            return
        try:
            result = self.db.batch_update_product_category(
                [int(iid) for iid in selected], category
            )
        except (ValueError, DatabaseError) as exc:
            logger.exception("批量修改商品类别失败")
            messagebox.showerror("批量修改失败", str(exc))
            return
        except Exception:
            logger.exception("批量修改商品类别发生未知异常")
            messagebox.showerror("批量修改失败", "发生未知错误，详情请查看 cashier.log")
            return
        self.prod_tree.selection_remove(*self.prod_tree.selection())
        self._clear_product_form()
        self._refresh_product_related_views()
        messagebox.showinfo(
            "批量修改完成",
            "成功更新 %d 个商品，跳过 %d 个商品。" %
            (result["updated"], result["skipped"]),
        )

    def _batch_delete_products(self) -> None:
        """确认并删除商品管理列表中的全部选中商品。"""
        selected = tuple(self.prod_tree.selection())
        if not selected:
            messagebox.showwarning("未选择", "请使用 Ctrl/Shift 在商品列表中多选商品")
            return
        if not messagebox.askyesno("确认批量删除", "确定删除所选 %d 个商品吗？删除后可撤回。" % len(selected)):
            return
        try:
            result = self.db.batch_delete_products([int(iid) for iid in selected])
        except (ValueError, DatabaseError) as exc:
            logger.exception("批量删除商品失败")
            messagebox.showerror("批量删除失败", str(exc))
            return
        except Exception:
            logger.exception("批量删除商品发生未知异常")
            messagebox.showerror("批量删除失败", "发生未知错误，详情请查看 cashier.log")
            return
        self.prod_tree.selection_remove(*self.prod_tree.selection())
        self._clear_product_form()
        self._refresh_product_related_views()
        messagebox.showinfo("批量删除完成", "成功删除 %d 个商品，跳过 %d 个商品。" %
                            (result["deleted"], result["skipped"]))

    def _undo_last_product_operation(self) -> None:
        """确认并撤回最后一次商品管理操作。"""
        try:
            operation = self.db.get_last_product_operation()
        except Exception:
            logger.exception("读取商品操作日志失败")
            messagebox.showerror("读取失败", "无法读取商品操作记录，详情请查看 cashier.log")
            return
        if operation is None:
            messagebox.showinfo("无法撤回", "没有可撤回的商品管理操作")
            return
        operation_type = str(operation.get("operation_type") or "未知操作")
        created_at = str(operation.get("created_at") or "")
        if not messagebox.askyesno(
            "确认撤回",
            "确定撤回上一次商品管理操作吗？\n\n操作：%s\n时间：%s" %
            (operation_type, created_at),
        ):
            return
        try:
            result = self.db.undo_last_product_operation()
        except DatabaseError as exc:
            logger.exception("撤回商品管理操作失败")
            messagebox.showerror("撤回失败", str(exc))
            return
        except Exception:
            logger.exception("撤回商品管理操作发生未知异常")
            messagebox.showerror("撤回失败", "发生未知错误，详情请查看 cashier.log")
            return
        self._clear_product_form()
        self._refresh_product_related_views()
        messagebox.showinfo("撤回成功", "已撤回上一次%s操作。" % result["operation_type"])

    def _fill_product_form(self, p: Dict[str, Any]) -> None:
        """用产品数据填充表单并选中列表对应行。"""
        self.prod_form_vars["id"].set(p["id"])
        self.prod_form_vars["barcode"].set(p.get("barcode") or "")
        self.prod_form_vars["name"].set(p["name"])
        self.prod_form_vars["category"].set(p.get("category") or "其他")
        self.prod_form_vars["cost"].set(str(p["cost_price"]))
        self.prod_form_vars["sell"].set(str(p["sell_price"]))
        self.prod_form_vars["mp"].set(f"{p['member_price']:.2f}" if p.get("member_price") else "")
        self.prod_form_vars["stock"].set(str(p["stock"]))
        self.prod_form_vars["low"].set(str(p["low_stock"]))
        # 滚动到可见（选中由 TreeviewSelect 事件保证）

    def _on_product_select(self, _event=None):
        sel = self.prod_tree.selection()
        if not sel:
            return
        try:
            p = self.db.get_product(int(sel[0]))
        except Exception:
            return
        if p is None:
            return
        self._fill_product_form(p)
        # 确保选中行可见
        iid = str(p["id"])
        if self.prod_tree.exists(iid):
            self.prod_tree.see(iid)

    def _collect_product_form(self) -> Dict[str, Any]:
        name = self.prod_form_vars["name"].get().strip()
        if not name:
            raise ValueError("「名称」不能为空")
        try:
            cost = float(self.prod_form_vars["cost"].get() or 0)
            sell = float(self.prod_form_vars["sell"].get() or 0)
            mp = self.prod_form_vars["mp"].get().strip()
            member_price = float(mp) if mp else None
            stock = int(float(self.prod_form_vars["stock"].get() or 0))
            low = int(float(self.prod_form_vars["low"].get() or 10))
        except (TypeError, ValueError):
            raise ValueError("价格/库存/预警线 必须是有效数字") from None
        return {
            "barcode": self.prod_form_vars["barcode"].get().strip() or None,
            "name": name, "category": self.prod_form_vars["category"].get().strip() or "其他",
            "cost_price": cost, "sell_price": sell, "member_price": member_price,
            "stock": stock, "low_stock": low,
        }

    def _add_product(self) -> None:
        try:
            d = self._collect_product_form()
            pid = self.db.add_product(d["name"], d["category"], d["cost_price"], d["sell_price"],
                                      d["stock"], d["low_stock"], d["barcode"], d["member_price"])
        except (ValueError, DatabaseError) as exc:
            logger.exception("新增商品失败")
            messagebox.showerror("新增失败", str(exc))
            return
        except Exception:
            logger.exception("新增商品发生未知异常")
            messagebox.showerror("新增失败", "发生未知错误，详情请查看 cashier.log")
            return
        messagebox.showinfo("成功", f"商品「{d['name']}」已添加 (ID: {pid})")
        self._clear_product_form()
        self._refresh_product_related_views()

    def _update_product(self) -> None:
        pid = self.prod_form_vars["id"].get()
        if not pid:
            messagebox.showwarning("提示", "请先在列表中选择商品")
            return
        try:
            d = self._collect_product_form()
            self.db.update_product(int(pid), d["name"], d["category"], d["cost_price"], d["sell_price"],
                                   d["stock"], d["low_stock"], d["barcode"], d["member_price"])
        except (ValueError, DatabaseError) as exc:
            logger.exception("保存商品失败")
            messagebox.showerror("保存失败", str(exc))
            return
        except Exception:
            logger.exception("保存商品发生未知异常")
            messagebox.showerror("保存失败", "发生未知错误，详情请查看 cashier.log")
            return
        messagebox.showinfo("成功", "商品信息已更新")
        self._refresh_product_related_views()

    def _delete_product(self) -> None:
        pid = self.prod_form_vars["id"].get()
        if not pid:
            messagebox.showwarning("提示", "请先选择商品")
            return
        name = self.prod_form_vars["name"].get() or f"ID {pid}"
        if not messagebox.askyesno("确认删除", f"确定删除商品「{name}」吗？"):
            return
        try:
            self.db.delete_product(int(pid))
        except DatabaseError as exc:
            logger.exception("删除商品失败")
            messagebox.showerror("删除失败", str(exc))
            return
        except Exception:
            logger.exception("删除商品发生未知异常")
            messagebox.showerror("删除失败", "发生未知错误，详情请查看 cashier.log")
            return
        messagebox.showinfo("成功", "商品已删除")
        self._clear_product_form()
        self._refresh_product_related_views()

    def _clear_product_form(self) -> None:
        for k, v in self.prod_form_vars.items():
            if k == "category":
                v.set("其他")
            elif k == "low":
                v.set("10")
            else:
                v.set("")
    # ------------------------------------------------------------------ #
    # 会员与折扣
    # ------------------------------------------------------------------ #
    def _build_members_tab(self) -> None:
        top = ttk.Frame(self.tab_members)
        top.pack(fill="both", expand=True)

        left = ttk.LabelFrame(top, text="会员管理", padding=6)
        left.pack(side="left", fill="both", expand=True, padx=(0, 6))

        self.member_search_var = tk.StringVar()
        self.member_search_var.trace_add("write", lambda *_: self._refresh_members_tab())
        srow = ttk.Frame(left)
        srow.pack(fill="x", pady=(0, 4))
        ttk.Entry(srow, textvariable=self.member_search_var).pack(side="left", fill="x", expand=True)
        ttk.Label(srow, text="≥3位模糊", foreground="gray", font=(UI_FONT, 8)).pack(side="left", padx=(4, 0))
        ttk.Button(srow, text="刷新", command=self._refresh_members_tab, width=6).pack(side="left", padx=(4, 0))

        self.member_tree = self._build_tree(
            left, (("id", "ID", 45, "center"), ("phone", "手机号", 105, "center"),
                   ("gender", "性别", 42, "center"), ("name", "姓名", 80, "w"),
                   ("points", "积分", 55, "center"), ("created", "注册时间", 125, "center")),
            height=12)
        self.member_tree.pack(fill="both", expand=True)
        self._make_sortable(self.member_tree, {"id"}, self._refresh_members_tab)
        self.member_tree.bind("<<TreeviewSelect>>", self._on_member_select)

        mform = ttk.LabelFrame(left, text="编辑会员（点击列表行填充）", padding=8)
        mform.pack(fill="x", pady=(6, 0))
        self.member_form_vars: Dict[str, tk.Variable] = {
            "id": tk.StringVar(), "phone": tk.StringVar(), "gender": tk.StringVar(), "name": tk.StringVar(),
        }
        mrow = ttk.Frame(mform)
        mrow.pack(fill="x", pady=2)
        ttk.Label(mrow, text="手机号*").pack(side="left", padx=(8, 2))
        ttk.Entry(mrow, textvariable=self.member_form_vars["phone"], width=13).pack(side="left")
        ttk.Label(mrow, text="性别").pack(side="left", padx=(8, 2))
        ttk.Combobox(mrow, textvariable=self.member_form_vars["gender"], values=["", "男", "女"],
                     width=4, state="normal").pack(side="left")
        ttk.Label(mrow, text="姓名").pack(side="left", padx=(8, 2))
        ttk.Entry(mrow, textvariable=self.member_form_vars["name"], width=11).pack(side="left")
        mbtns = ttk.Frame(mform)
        mbtns.pack(fill="x", pady=(6, 0))
        ttk.Button(mbtns, text="新增会员", command=self._add_member).pack(side="left", padx=4)
        ttk.Button(mbtns, text="保存修改", command=self._update_member).pack(side="left", padx=4)
        ttk.Button(mbtns, text="删除会员", command=self._delete_member).pack(side="left", padx=4)
        ttk.Button(mbtns, text="清空表单", command=self._clear_member_form).pack(side="left", padx=4)

        # 积分兑换区
        pts_frame = ttk.LabelFrame(mform, text="积分兑换", padding=6)
        pts_frame.pack(fill="x", pady=(8, 0))
        self.pts_selected_label = ttk.Label(pts_frame, text="请先在列表选择会员", foreground="gray")
        self.pts_selected_label.pack(anchor="w")
        prow = ttk.Frame(pts_frame)
        prow.pack(fill="x", pady=(4, 0))
        ttk.Label(prow, text="积分变动:").pack(side="left")
        self.pts_delta_var = tk.StringVar()
        ttk.Entry(prow, textvariable=self.pts_delta_var, width=8).pack(side="left", padx=4)
        ttk.Label(prow, text="（正数增加/负数扣减）", foreground="gray").pack(side="left")
        rrow = ttk.Frame(pts_frame)
        rrow.pack(fill="x", pady=(4, 0))
        ttk.Label(rrow, text="备注:").pack(side="left")
        self.pts_remark_var = tk.StringVar()
        ttk.Entry(rrow, textvariable=self.pts_remark_var, width=24).pack(side="left", padx=4)
        ttk.Button(pts_frame, text="确认兑换", command=self._adjust_points).pack(fill="x", pady=(6, 0))

        # 折扣价区
        right = ttk.LabelFrame(top, text="商品会员价设置", padding=6)
        right.pack(side="right", fill="both", expand=True)
        self.discount_tree = self._build_tree(
            right, (("id", "ID", 45, "center"), ("name", "商品", 140, "w"),
                    ("price", "原售价", 70, "e"), ("mprice", "会员价", 70, "e"),
                    ("stock", "库存", 50, "e")), height=12)
        self.discount_tree.pack(fill="both", expand=True)
        self._make_sortable(self.discount_tree, {"id", "price", "mprice", "stock"}, self._refresh_members_tab)
        self.discount_tree.bind("<<TreeviewSelect>>", self._on_discount_select)

        dform = ttk.LabelFrame(right, text="设置折扣价", padding=8)
        dform.pack(fill="x", pady=(6, 0))
        self.discount_form_vars: Dict[str, tk.Variable] = {
            "id": tk.StringVar(), "name": tk.StringVar(value="（请选择商品）"),
            "price": tk.StringVar(), "mprice": tk.StringVar(),
        }
        ttk.Label(dform, textvariable=self.discount_form_vars["name"], wraplength=240).pack(anchor="w")
        drow = ttk.Frame(dform)
        drow.pack(fill="x", pady=(6, 2))
        ttk.Label(drow, text="原售价:").pack(side="left")
        ttk.Label(drow, textvariable=self.discount_form_vars["price"], foreground="gray").pack(side="left", padx=(4, 16))
        ttk.Label(drow, text="会员价:").pack(side="left")
        ttk.Entry(drow, textvariable=self.discount_form_vars["mprice"], width=10).pack(side="left", padx=4)
        ttk.Label(dform, text="留空或填 0 = 无会员折扣，按原价销售", foreground="gray").pack(anchor="w")
        ttk.Button(dform, text="保存会员价", command=self._save_member_price, width=20).pack(fill="x", pady=(6, 0))

    def _refresh_members_tab(self) -> None:
        try:
            members = self.db.search_members_fuzzy(self.member_search_var.get())
            products = self.db.search_products()
        except Exception:
            logger.exception("刷新会员页失败")
            return
        mrows = []
        for m in members:
            mrows.append(((m["id"], m["phone"], m.get("gender", ""), m["name"],
                          m.get("points", 0), m["created_at"]),
                          str(m["id"]), ()))
        self._fill_tree(self.member_tree, mrows)
        drows = []
        for p in products:
            mp = p.get("member_price")
            drows.append(((p["id"], p["name"], f"{p['sell_price']:.2f}",
                           f"{mp:.2f}" if mp else "—", p["stock"]),
                          str(p["id"]), ("member",) if mp else ()))
        self._fill_tree(self.discount_tree, drows)

    def _on_member_select(self, _event=None):
        sel = self.member_tree.selection()
        if not sel:
            return
        try:
            m = self.db.get_member(int(sel[0]))
        except Exception:
            return
        if m:
            self._fill_member_form(m)
            pts = m.get("points", 0)
            name = (m.get("name") or "").strip() or m["phone"]
            self.pts_selected_label.config(
                text=f"{name} — 当前积分: {pts}", foreground="black")

    def _fill_member_form(self, m: Dict[str, Any]) -> None:
        self.member_form_vars["id"].set(m["id"])
        self.member_form_vars["phone"].set(m["phone"])
        self.member_form_vars["gender"].set(m.get("gender", ""))
        self.member_form_vars["name"].set(m["name"])

    def _collect_member_form(self) -> Dict[str, Any]:
        phone = self.member_form_vars["phone"].get().strip()
        gender = self.member_form_vars["gender"].get().strip()
        name = self.member_form_vars["name"].get().strip()
        if not phone:
            raise ValueError("「手机号」不能为空")
        if not phone.isdigit():
            raise ValueError("「手机号」必须为数字")
        return {"phone": phone, "gender": gender, "name": name}

    def _add_member(self) -> None:
        try:
            data = self._collect_member_form()
            mid = self.db.add_member(data["phone"], data["gender"], data["name"])
        except (ValueError, DatabaseError) as exc:
            messagebox.showerror("新增失败", str(exc))
            return
        messagebox.showinfo("成功", f"会员 {data['phone']} 已注册 (ID: {mid})")
        self._clear_member_form()
        self._refresh_members_tab()

    def _update_member(self) -> None:
        mid = self.member_form_vars["id"].get()
        if not mid:
            messagebox.showwarning("提示", "请先选择会员")
            return
        try:
            data = self._collect_member_form()
            self.db.update_member(int(mid), data["phone"], data["gender"], data["name"])
        except (ValueError, DatabaseError) as exc:
            messagebox.showerror("保存失败", str(exc))
            return
        messagebox.showinfo("成功", "会员信息已更新")
        self._refresh_members_tab()

    def _delete_member(self) -> None:
        mid = self.member_form_vars["id"].get()
        if not mid:
            messagebox.showwarning("提示", "请先选择会员")
            return
        phone = self.member_form_vars["phone"].get() or f"ID {mid}"
        if not messagebox.askyesno("确认删除", f"确定删除会员「{phone}」吗？"):
            return
        try:
            self.db.delete_member(int(mid))
        except Exception:
            messagebox.showerror("删除失败", "发生未知错误")
            return
        messagebox.showinfo("成功", "会员已删除")
        self._clear_member_form()
        self._refresh_members_tab()

    def _clear_member_form(self) -> None:
        for var in self.member_form_vars.values():
            var.set("")
        self.pts_selected_label.config(text="请先在列表选择会员", foreground="gray")
        self.pts_delta_var.set("")
        self.pts_remark_var.set("")

    def _adjust_points(self) -> None:
        sel = self.member_tree.selection()
        if not sel:
            messagebox.showwarning("提示", "请先在上方列表中选择一个会员")
            return
        try:
            delta = int(self.pts_delta_var.get().strip())
        except ValueError:
            messagebox.showerror("输入错误", "积分变动必须为整数")
            return
        if delta == 0:
            messagebox.showwarning("提示", "积分变动不能为 0")
            return
        remark = self.pts_remark_var.get().strip()
        if not remark:
            messagebox.showwarning("提示", "请填写兑换备注")
            return
        member_id = int(sel[0])
        try:
            self.db.adjust_member_points(member_id, delta, remark)
        except DatabaseError as exc:
            messagebox.showerror("兑换失败", str(exc))
            return
        except Exception:
            logger.exception("积分兑换异常")
            messagebox.showerror("兑换失败", "发生未知错误")
            return
        self.pts_delta_var.set("")
        self.pts_remark_var.set("")
        self._refresh_members_tab()
        self._refresh_sales_tab()
        self._set_status(f"会员积分已调整 {delta:+d}", "green")

    def _on_discount_select(self, _event=None):
        sel = self.discount_tree.selection()
        if not sel:
            return
        try:
            p = self.db.get_product(int(sel[0]))
        except Exception:
            return
        if p:
            self.discount_form_vars["id"].set(str(p["id"]))
            self.discount_form_vars["name"].set(p["name"])
            self.discount_form_vars["price"].set(f"{p['sell_price']:.2f}")
            mp = p.get("member_price")
            self.discount_form_vars["mprice"].set(f"{mp:.2f}" if mp else "")

    def _save_member_price(self) -> None:
        pid = self.discount_form_vars["id"].get()
        if not pid:
            messagebox.showwarning("提示", "请先在列表中双击选择商品")
            return
        mp_str = self.discount_form_vars["mprice"].get().strip()
        mp_val = float(mp_str) if mp_str else None
        try:
            p = self.db.get_product(int(pid))
            if p is None:
                return
            self.db.update_product(int(pid), p["name"], p["category"], p["cost_price"], p["sell_price"],
                                   p["stock"], p["low_stock"], p.get("barcode"), mp_val)
        except Exception:
            messagebox.showerror("保存失败", "发生未知错误")
            return
        messagebox.showinfo("成功", "会员价已更新")
        self._refresh_members_tab()

    # ------------------------------------------------------------------ #
    # 库存管理
    # ------------------------------------------------------------------ #
    def _build_stock_tab(self) -> None:
        top = ttk.Frame(self.tab_stock)
        top.pack(fill="both", expand=True)

        left = ttk.LabelFrame(top, text="商品库存", padding=6)
        left.pack(side="left", fill="both", expand=True, padx=(0, 6))

        self.stock_tree = self._build_tree(
            left, (("id", "ID", 45, "center"), ("name", "名称", 150, "w"),
                   ("category", "类别", 55, "center"), ("cost", "进价", 55, "e"),
                   ("stock", "库存", 50, "e"),
                   ("low", "预警线", 50, "e"), ("status", "状态", 55, "center")),
            height=14)
        self.stock_tree.pack(fill="both", expand=True)
        self.stock_tree.tag_configure("low", foreground="red")
        self._make_sortable(self.stock_tree, {"id", "cost", "stock", "low"}, self._refresh_stock_tab)
        self.stock_tree.bind("<<TreeviewSelect>>", self._on_stock_select)
        self.stock_tree.bind("<Double-1>", lambda _: self._stock_action(1))

        sib = ttk.Frame(left)
        sib.pack(fill="x", pady=(4, 0))
        ttk.Label(sib, text="条码:").pack(side="left")
        self.stock_barcode_var = tk.StringVar()
        stock_bc_entry = ttk.Entry(sib, textvariable=self.stock_barcode_var, width=16)
        stock_bc_entry.pack(side="left", padx=(2, 8))
        stock_bc_entry.bind("<Return>", self._on_stock_barcode)
        self._setup_placeholder(stock_bc_entry, self.stock_barcode_var, "可输入条码")
        def _stock_barcode_search():
            q = self.stock_barcode_var.get().strip()
            if not q or q == "可输入条码":
                return
            results = self._fuzzy_barcode_search(q)
            if not results:
                self._set_status(f"未找到条码: {q}", "red")
            elif len(results) == 1 and results[0][0] == 1.0:
                self._stock_barcode_lookup(results[0][1].get("barcode", ""))
            else:
                self._show_barcode_search_popup(
                    q, results,
                    lambda p: self._stock_barcode_lookup(p.get("barcode", ""))
                )
        ttk.Button(sib, text="搜索", command=_stock_barcode_search, width=5).pack(side="left", padx=(2, 4))
        ttk.Button(sib, text="刷新库存/日志", command=self._refresh_stock_tab).pack(side="left")
        ttk.Button(sib, text="导入库存 (Excel)", command=self._import_stock_ui, width=18).pack(side="left", padx=(8, 0))

        right = ttk.Frame(top)
        right.pack(side="right", fill="y")

        op = ttk.LabelFrame(right, text="库存操作", padding=8)
        op.pack(fill="x", pady=(0, 6))
        self.stock_name_var = tk.StringVar(value="（请在列表选择商品）")
        ttk.Label(op, textvariable=self.stock_name_var, wraplength=200).pack(anchor="w")
        ttk.Separator(op).pack(fill="x", pady=4)
        self.stock_delta_var = tk.StringVar(value="1")
        ttk.Label(op, text="数量（正数入库/负数出库）:").pack(anchor="w")
        ttk.Entry(op, textvariable=self.stock_delta_var, width=10).pack(fill="x", pady=(2, 4))
        self.stock_note_var = tk.StringVar()
        ttk.Label(op, text="备注:").pack(anchor="w")
        ttk.Entry(op, textvariable=self.stock_note_var, width=24).pack(fill="x", pady=(2, 4))
        ttk.Button(op, text="执行操作", command=lambda: self._stock_action(0)).pack(fill="x")

        ttk.Separator(op).pack(fill="x", pady=6)
        ttk.Label(op, text="价格波动（加权平均进价）", font=("", 9, "bold")).pack(anchor="w")
        self.price_new_price_var = tk.StringVar(value="")
        ttk.Label(op, text="新进价:").pack(anchor="w")
        ttk.Entry(op, textvariable=self.price_new_price_var, width=10).pack(fill="x", pady=(1, 2))
        self.price_new_qty_var = tk.StringVar(value="")
        ttk.Label(op, text="新入库数量:").pack(anchor="w")
        ttk.Entry(op, textvariable=self.price_new_qty_var, width=10).pack(fill="x", pady=(1, 4))
        ttk.Button(op, text="价格波动计算", command=self._price_fluctuation).pack(fill="x")

        log_frame = ttk.LabelFrame(right, text="库存日志", padding=6)
        log_frame.pack(fill="both", expand=True)
        self.stock_log_tree = self._build_tree(
            log_frame, (("date", "时间", 110, "center"), ("type", "类型", 60, "center"),
                        ("qty", "数量", 50, "e"), ("after", "库存", 50, "e"),
                        ("cost", "进价", 55, "e"), ("note", "备注", 130, "w")),
            height=10)
        self.stock_log_tree.pack(fill="both", expand=True)

        log_btn = ttk.Frame(log_frame)
        log_btn.pack(fill="x", pady=(4, 0))
        ttk.Button(log_btn, text="撤销选中记录", command=self._undo_stock_log).pack(side="left")

    def _refresh_stock_tab(self) -> None:
        try:
            products = self.db.search_products()
        except Exception:
            logger.exception("查询库存失败")
            return
        rows = []
        for p in products:
            cost = p.get("cost_price", 0) or 0
            s = p["stock"]
            l = p["low_stock"]
            status = "⚠ 低库存" if s <= l else "正常"
            tag = ("low",) if s <= l else ()
            rows.append(((p["id"], p["name"], p.get("category", ""), f"¥{cost:.2f}", s, l, status),
                         str(p["id"]), tag))
        self._fill_tree(self.stock_tree, rows)
        self.stock_tree.tag_configure("low", foreground="red")

    def _on_stock_select(self, _event=None):
        sel = self.stock_tree.selection()
        if not sel:
            return
        try:
            p = self.db.get_product(int(sel[0]))
        except Exception:
            return
        if p is None:
            return
        self.stock_name_var.set(f"{p['name']}（当前库存: {p['stock']}）")
        self._refresh_stock_logs(int(sel[0]))

    def _on_stock_barcode(self, _event=None) -> None:
        code = self.stock_barcode_var.get().strip()
        if not code or code == "可输入条码":
            return
        self._stock_barcode_lookup(code)

    def _stock_barcode_lookup(self, code: str) -> None:
        try:
            products = self.db.get_products_by_barcode(code)
        except Exception:
            return
        if products:
            if len(products) == 1:
                self._stock_select_and_refresh(products[0])
            else:
                self._show_barcode_search_popup(
                    code, [(1.0, p) for p in products],
                    self._stock_select_and_refresh)
            self.stock_barcode_var.set("")
            return
        # 精确匹配失败 → 模糊搜索
        results = self._fuzzy_barcode_search(code)
        if not results:
            self.stock_barcode_var.set("")
            messagebox.showwarning("未找到", f"未找到条码: {code}")
            return
        if len(results) == 1 and results[0][0] >= 0.9:
            self._stock_select_and_refresh(results[0][1])
        else:
            self._show_barcode_search_popup(code, results, self._stock_select_and_refresh)
        self.stock_barcode_var.set("")

    def _stock_select_and_refresh(self, p: Dict[str, Any]) -> None:
        """在库存树中选中商品并加载日志。"""
        pid_str = str(p["id"])
        children = self.stock_tree.get_children()
        if pid_str in children:
            self.stock_tree.selection_set(pid_str)
            self.stock_tree.see(pid_str)
            self.stock_tree.focus(pid_str)
        self._on_stock_select()

    def _refresh_stock_logs(self, pid: int) -> None:
        try:
            logs = self.db.get_stock_logs(pid, 50)
            self._stock_logs_cache = {str(l["id"]): l for l in logs}
            rows = [((l["created_at"], l["change_type"], l["quantity"], l["stock_after"],
                      f"{l['cost_price']:.2f}" if l.get("cost_price") is not None else "—",
                      self._clean_stock_note(l["note"])),
                     str(l["id"]), ()) for l in logs]
            self._fill_tree(self.stock_log_tree, rows)
        except Exception:
            logger.exception("刷新库存日志失败")

    def _undo_stock_log(self) -> None:
        sel = self.stock_log_tree.selection()
        if not sel:
            messagebox.showwarning("未选择", "请先在库存日志中选中一条记录")
            return
        log_id = sel[0]
        log = getattr(self, "_stock_logs_cache", {}).get(log_id)
        if log is None:
            return
        NL = chr(10)
        msg = "确定撤销以下库存变动吗？" + NL + NL
        msg += "商品：" + str(log['product_name']) + NL
        msg += "操作：" + str(log['change_type']) + " " + str(log['quantity']) + " -> 库存 " + str(log['stock_after']) + NL
        if log.get("cost_price") is not None:
            msg += "进价：" + str(log["cost_price"]) + NL
        msg += "备注：" + str(log['note']) + NL + NL
        msg += "撤销后将执行反向操作并记录新日志。"
        answer = messagebox.askyesno("确认撤销", msg)
        if not answer:
            return
        reverse_qty = -log["quantity"]
        reverse_note = "撤销日志#" + str(log['id']) + "（原" + str(log['change_type']) + " " + str(log['quantity']) + "，备注：" + str(log['note']) + "）"
        try:
            self.db.adjust_stock(log["product_id"], reverse_qty, reverse_note)
            # 如果是价格波动入库，还需要回退进价（从日志note中解析旧进价）
            if log["change_type"] == "价格波动入库":
                old_cost = self._parse_old_cost_from_note(log.get("note") or "")
                self.db.set_product_cost_price(log["product_id"], old_cost)
        except DatabaseError as exc:
            messagebox.showerror("撤销失败", str(exc))
            return
        messagebox.showinfo("已撤销", "「" + str(log['product_name']) + "」库存已回退")
        self._refresh_stock_tab()
        self.after(10, lambda: self._refresh_stock_logs(log["product_id"]))

    @staticmethod
    def _parse_old_cost_from_note(note: str) -> float:
        """从价格波动日志的note中解析旧进价。格式：旧进价=XX.XX|用户备注"""
        try:
            prefix_end = note.index("|")
            old_cost_str = note[len("旧进价="):prefix_end]
            return float(old_cost_str)
        except (ValueError, IndexError):
            return 0.0

    @staticmethod
    def _clean_stock_note(note: str) -> str:
        """在UI和导出中隐藏内部标记前缀。"""
        if note.startswith("旧进价=") and "|" in note:
            return note[note.index("|") + 1:]
        return note

    def _stock_action(self, mode: int) -> None:
        sel = self.stock_tree.selection()
        if not sel:
            return
        try:
            p = self.db.get_product(int(sel[0]))
        except Exception:
            return
        if p is None:
            return
        if mode == 0:
            try:
                delta = int(float(self.stock_delta_var.get()))
            except (TypeError, ValueError):
                messagebox.showerror("输入错误", "数量必须是整数")
                return
            note = self.stock_note_var.get().strip() or "手动调整"
            try:
                self.db.adjust_stock(p["id"], delta, note)
            except DatabaseError as exc:
                messagebox.showerror("操作失败", str(exc))
                return
            messagebox.showinfo("成功", f"「{p['name']}」库存已调整（{'+' if delta > 0 else ''}{delta}）")
            pid = p["id"]
            self._refresh_stock_tab()
            self.after(10, lambda: self._refresh_stock_logs(pid))
        else:
            self.stock_delta_var.set("1")
            self.stock_note_var.set("")

    def _price_fluctuation(self) -> None:
        """价格波动入库：加权平均计算新进价。"""
        sel = self.stock_tree.selection()
        if not sel:
            messagebox.showwarning("提示", "请先在商品列表中选择一个商品")
            return
        try:
            p = self.db.get_product(int(sel[0]))
        except Exception:
            return
        if p is None:
            return
        try:
            new_price = float(self.price_new_price_var.get().strip())
            new_qty = int(float(self.price_new_qty_var.get().strip()))
        except (TypeError, ValueError):
            messagebox.showerror("输入错误", "新进价和新入库数量必须是有效数字")
            return
        if new_price <= 0:
            messagebox.showerror("输入错误", "新进价必须大于0")
            return
        if new_qty <= 0:
            messagebox.showerror("输入错误", "新入库数量必须大于0")
            return
        try:
            result = self.db.adjust_stock_price(p["id"], new_qty, new_price,
                                                self.stock_note_var.get().strip() or "价格波动")
        except DatabaseError as exc:
            messagebox.showerror("操作失败", str(exc))
            return
        msg = (
            f"「{p['name']}」\n"
            f"旧进价: ¥{result['old_cost']:.2f}  →  新进价: ¥{result['new_cost']:.2f}\n"
            f"旧库存: {result['old_stock']}  →  新库存: {result['new_stock']}"
        )
        messagebox.showinfo("价格波动完成", msg)
        self._refresh_stock_tab()
        self.after(10, lambda: self._refresh_stock_logs(p["id"]))

    # ------------------------------------------------------------------ #
    # 销售记录
    # ------------------------------------------------------------------ #
    def _build_sales_tab(self) -> None:
        top = ttk.Frame(self.tab_sales)
        top.pack(fill="x", padx=8, pady=(8, 4))

        self.sale_search_var = tk.StringVar()
        self.sale_search_var.trace_add("write", lambda *_: self._refresh_sales_tab())
        ttk.Entry(top, textvariable=self.sale_search_var, width=20).pack(side="left", padx=(0, 6))
        ttk.Label(top, text="日期从:").pack(side="left")
        self.sale_start_var = tk.StringVar(value="")
        ttk.Entry(top, textvariable=self.sale_start_var, width=12).pack(side="left", padx=4)
        ttk.Label(top, text="到:").pack(side="left")
        self.sale_end_var = tk.StringVar(value="")
        ttk.Entry(top, textvariable=self.sale_end_var, width=12).pack(side="left", padx=4)
        ttk.Button(top, text="查询", command=self._refresh_sales_tab, width=6).pack(side="left", padx=(6, 0))

        body = ttk.Frame(self.tab_sales)
        body.pack(fill="both", expand=True, padx=8)
        body.columnconfigure(0, weight=3)  # 左：商品销售历史
        body.columnconfigure(1, weight=5)  # 右：销售记录

        # ===== 左半边：商品销售历史 =====
        left = ttk.Frame(body)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        left.rowconfigure(0, weight=2)
        left.rowconfigure(1, weight=3)

        prod_box = ttk.LabelFrame(left, text="商品销售汇总（累计）", padding=4)
        prod_box.grid(row=0, column=0, sticky="nsew", pady=(0, 4))
        self.sale_prod_tree = self._build_tree(
            prod_box, (("name", "商品", 100, "w"), ("total_qty", "累计销量", 55, "e"),
                       ("total_revenue", "累计销售额", 75, "e")), height=8)
        self.sale_prod_tree.pack(fill="both", expand=True)
        self.sale_prod_tree.bind("<<TreeviewSelect>>", self._on_sale_prod_select)

        prod_detail_box = ttk.LabelFrame(left, text="商品销售明细", padding=4)
        prod_detail_box.grid(row=1, column=0, sticky="nsew")
        self.sale_prod_detail_tree = self._build_tree(
            prod_detail_box, (("date", "日期", 90, "center"), ("order_no", "单号", 70, "center"),
                              ("qty", "数量", 40, "e"), ("subtotal", "小计", 60, "e")), height=6)
        self.sale_prod_detail_tree.pack(fill="both", expand=True)

        # ===== 右半边：原有销售记录 =====
        right = ttk.Frame(body)
        right.grid(row=0, column=1, sticky="nsew", padx=(4, 0))

        self.sale_tree = self._build_tree(
            right, (("order_no", "单号", 90, "center"), ("status", "状态", 45, "center"),
                   ("total", "总金额", 60, "e"),
                   ("discount", "优惠", 50, "e"), ("paid", "实收", 55, "e"),
                   ("change", "找零", 50, "e"), ("member", "会员", 65, "center"),
                   ("items", "商品数", 45, "center"), ("time", "时间", 110, "center")),
            height=8)
        self.sale_tree.pack(fill="x")
        self._make_sortable(self.sale_tree, {"order_no", "total", "discount", "paid", "change", "items"},
                            self._refresh_sales_tab)
        self.sale_tree.bind("<<TreeviewSelect>>", self._on_sale_select)

        detail = ttk.LabelFrame(right, text="销售明细", padding=6)
        detail.pack(fill="both", expand=True, pady=(4, 0))
        self.sale_item_tree = self._build_tree(
            detail, (("pid", "商品ID", 55, "center"), ("name", "商品", 160, "w"),
                     ("price", "单价", 55, "e"), ("qty", "数量", 45, "center"),
                     ("subtotal", "小计", 70, "e")),
            height=6)
        self.sale_item_tree.pack(fill="both", expand=True)
        sbtn = ttk.Frame(detail)
        sbtn.pack(fill="x", pady=(4, 0))
        ttk.Button(sbtn, text="↩ 退货", command=self._return_sale).pack(side="left")
        ttk.Button(sbtn, text="🖨 查看小票", command=self._show_sale_receipt).pack(side="right")

    def _refresh_sales_tab(self) -> None:
        try:
            sales = self.db.search_sales(self.sale_search_var.get(),
                                         self.sale_start_var.get(), self.sale_end_var.get())
        except Exception:
            logger.exception("查询销售失败")
            return
        member_map = self.db._member_phone_map()
        rows = []
        for s in sales:
            member = member_map.get(s["member_id"]) or ""
            status = "↩已退" if s.get("returned") else ""
            tag = ("returned",) if s.get("returned") else ()
            rows.append(((s.get("order_no") or str(s["id"]), status, f"{s['total_amount']:.2f}", f"{s['discount']:.2f}",
                          f"{s['paid_amount']:.2f}", f"{s['change_amount']:.2f}",
                          member, s["item_count"], s["created_at"]),
                         str(s["id"]), tag))
        self._fill_tree(self.sale_tree, rows)
        self.sale_tree.tag_configure("returned", foreground="gray")

        # 左半边：商品销售汇总
        try:
            prods = self.db.get_product_sales_summary()
        except Exception:
            logger.exception("商品销售汇总查询失败")
            return
        prod_rows = [((p["name"], p["total_qty"], f"{p['total_revenue']:.2f}"),
                      str(p["product_id"]), ()) for p in prods]
        self._fill_tree(self.sale_prod_tree, prod_rows)

    def _on_sale_prod_select(self, _event=None):
        """左半边商品树选中时，显示该商品所有销售明细。"""
        sel = self.sale_prod_tree.selection()
        if not sel:
            return
        try:
            details = self.db.get_product_sale_details(int(sel[0]))
        except Exception:
            logger.exception("商品销售明细查询失败")
            return
        rows = [((d["created_at"][:10], d["order_no"] or str(d["sale_id"]),
                  d["quantity"], f"{d['subtotal']:.2f}"),
                 str(d["sale_id"]), ()) for d in details]
        self._fill_tree(self.sale_prod_detail_tree, rows)

    def _on_sale_select(self, _event=None):
        sel = self.sale_tree.selection()
        if not sel:
            return
        try:
            items = self.db.get_sale_items(int(sel[0]))
        except Exception:
            return
        if items:
            rows = [((it["product_id"], it["product_name"], f"{it['price']:.2f}",
                     it["quantity"], f"{it['subtotal']:.2f}"), str(it["id"]), ()) for it in items]
        else:
            # 积分兑换等无明细记录，显示 order_no 作为备注
            try:
                sale = self.db.get_sale(int(sel[0]))
                note = sale["order_no"] if sale else ""
            except Exception:
                note = ""
            rows = [((0, note or "（无明细）", "—", "—", "—"), "0", ())]
        self._fill_tree(self.sale_item_tree, rows)

    def _return_sale(self) -> None:
        """整单退货：确认后恢复库存并标记已退。"""
        sel = self.sale_tree.selection()
        if not sel:
            messagebox.showwarning("提示", "请先在上方列表中选择一条销售记录")
            return
        sale_id = int(sel[0])
        try:
            sale = self.db.get_sale(sale_id)
        except Exception:
            messagebox.showerror("错误", "查询销售记录失败")
            return
        if not sale:
            messagebox.showerror("错误", "销售记录不存在")
            return
        order_no = sale.get("order_no") or f"#{sale_id}"
        if sale.get("returned"):
            messagebox.showinfo("提示", "该单已退货，无需重复操作")
            return
        if not messagebox.askyesno(
            "确认退货",
            f"确定对销售单 {order_no} 执行整单退货？\n\n"
            f"金额: ¥{sale['total_amount']:.2f}\n"
            f"实收: ¥{sale['paid_amount']:.2f}\n\n"
            f"所有商品库存将恢复，此操作不可撤回。",
            icon="warning",
        ):
            return
        try:
            result = self.db.return_sale(sale_id)
        except DatabaseError as exc:
            messagebox.showerror("退货失败", str(exc))
            return
        except Exception:
            logger.exception("退货异常")
            messagebox.showerror("退货失败", "发生未知错误，详见 cashier.log")
            return
        self._refresh_sales_tab()
        self._refresh_stock_tab()
        self._refresh_product_list()
        self._refresh_products_tab()
        self._refresh_finance_tab()
        self._set_status(
            f"退货完成: 单号 {order_no}  ¥{result['total_amount']:.2f}  ({result['item_count']}件商品)",
            "green",
        )
        messagebox.showinfo("退货完成",
                            f"销售单 {order_no} 已退货\n\n"
                            f"退款: ¥{result['paid_amount']:.2f}\n"
                            f"商品库存已恢复")

    def _show_sale_receipt(self) -> None:
        """弹出小票详情窗口。"""
        sel = self.sale_tree.selection()
        if not sel:
            messagebox.showwarning("提示", "请先在上方列表中选择一条销售记录")
            return
        sale_id = int(sel[0])
        try:
            sale = self.db.get_sale(sale_id)
            items = self.db.get_sale_items(sale_id)
            order_no = sale.get("order_no") if sale else f"#{sale_id}"
        except Exception:
            messagebox.showerror("错误", "查询销售详情失败")
            return
        if not sale:
            messagebox.showerror("错误", "销售记录不存在")
            return

        win = tk.Toplevel(self)
        win.title(f"小票详情 — 单号 {order_no}")
        win.transient(self)
        win.grab_set()
        win.resizable(False, False)

        frm = ttk.Frame(win, padding=16)
        frm.pack(fill="both", expand=True)

        F = (UI_FONT, 11)
        FB = (UI_FONT, 12, "bold")
        FT = (UI_FONT, 16, "bold")

        # 头部
        ttk.Label(frm, text="烟酒店收银系统", font=(UI_FONT, 14, "bold")).pack()
        ttk.Label(frm, text=f"销售单号: {order_no}", font=FB).pack(pady=(2, 0))
        ttk.Label(frm, text=f"日期: {sale['created_at']}", font=F).pack()

        member_map = self.db._member_phone_map()
        member = member_map.get(sale.get("member_id")) or ""
        if member:
            ttk.Label(frm, text=f"会员: {member}", font=F, foreground="#d33").pack()

        ttk.Separator(frm, orient="horizontal").pack(fill="x", pady=6)

        # 明细表
        tree = ttk.Treeview(frm, columns=("name", "price", "qty", "subtotal"),
                            show="headings", height=min(len(items), 10))
        for cid, text, w, a in [("name", "商品", 180, "w"), ("price", "单价", 60, "e"),
                                 ("qty", "数量", 45, "center"), ("subtotal", "小计", 70, "e")]:
            tree.heading(cid, text=text)
            tree.column(cid, width=w, anchor=a)
        tree.pack(fill="x", pady=(0, 6))
        for it in items:
            tree.insert("", "end", values=(it["product_name"], f"{it['price']:.2f}",
                                            it["quantity"], f"{it['subtotal']:.2f}"))

        ttk.Separator(frm, orient="horizontal").pack(fill="x", pady=4)

        # 金额汇总
        info = ttk.Frame(frm)
        info.pack(fill="x")
        ttk.Label(info, text="商品总计:", font=F).pack(side="left")
        ttk.Label(info, text=f"¥{sale['total_amount']:.2f}", font=FB).pack(side="right")

        if sale["discount"] > 0:
            drow = ttk.Frame(frm)
            drow.pack(fill="x")
            ttk.Label(drow, text="优惠金额:", font=F, foreground="#d33").pack(side="left")
            ttk.Label(drow, text=f"-¥{sale['discount']:.2f}", font=FB, foreground="#d33").pack(side="right")

        payrow = ttk.Frame(frm)
        payrow.pack(fill="x")
        ttk.Label(payrow, text="实收金额:", font=F).pack(side="left")
        ttk.Label(payrow, text=f"¥{sale['paid_amount']:.2f}", font=FT, foreground="#060").pack(side="right")

        if sale["change_amount"] > 0:
            crow = ttk.Frame(frm)
            crow.pack(fill="x")
            ttk.Label(crow, text="找零:", font=F, foreground="#06c").pack(side="left")
            ttk.Label(crow, text=f"¥{sale['change_amount']:.2f}", font=FB, foreground="#06c").pack(side="right")

        ttk.Separator(frm, orient="horizontal").pack(fill="x", pady=6)
        ttk.Label(frm, text="谢谢惠顾！", font=(UI_FONT, 12), foreground="gray").pack()

        ttk.Button(frm, text="关闭", command=win.destroy, width=14).pack(pady=(10, 0))

        win.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - win.winfo_width()) // 2
        y = self.winfo_y() + (self.winfo_height() - win.winfo_height()) // 2
        win.geometry(f"+{x}+{y}")

    # ------------------------------------------------------------------ #
    # 财报分析
    # ------------------------------------------------------------------ #
    def _build_finance_tab(self) -> None:
        top = ttk.Frame(self.tab_finance)
        top.pack(fill="x", pady=(0, 6))

        self.fin_cards: Dict[str, tk.StringVar] = {}
        for idx, (key, title) in enumerate([
            ("today", "今日营收"), ("month", "本月营收"), ("year", "本年营收"), ("all", "累计营收"),
            ("inventory", "库存金额"),
        ]):
            card = ttk.LabelFrame(top, text=title, padding=6)
            card.grid(row=0, column=idx, padx=4, sticky="nsew")
            top.columnconfigure(idx, weight=1)
            var = tk.StringVar(value="--")
            ttk.Label(card, textvariable=var, font=(UI_FONT, 12, "bold"),
                      foreground="#000", justify="left").pack(anchor="w")
            self.fin_cards[key] = var
        bar = ttk.Frame(top)
        bar.grid(row=1, column=0, columnspan=5, sticky="ew", pady=(4, 0))
        ttk.Label(bar, text="自定义:").pack(side="left")
        self.fin_range_var = tk.StringVar(value="选择日期范围")
        self.fin_range_combo = ttk.Combobox(bar, textvariable=self.fin_range_var, width=14,
                                            state="readonly", font=(UI_FONT, 10))
        self.fin_range_combo["values"] = ["今天", "昨天", "本周", "上周", "本月", "上月",
                                           "近7天", "近30天", "本季度", "本年", "自定义..."]
        self.fin_range_combo.pack(side="left", padx=4)
        self.fin_range_combo.bind("<<ComboboxSelected>>", self._on_fin_range_select)
        # 自定义日期输入（默认隐藏）
        self.fin_custom_frame = ttk.Frame(bar)
        self.fin_range_start = ttk.Entry(self.fin_custom_frame, width=10)
        self.fin_range_start.pack(side="left", padx=2)
        ttk.Label(self.fin_custom_frame, text="—").pack(side="left")
        self.fin_range_end = ttk.Entry(self.fin_custom_frame, width=10)
        self.fin_range_end.pack(side="left", padx=2)
        ttk.Button(self.fin_custom_frame, text="查询", command=self._refresh_finance_range, width=6).pack(side="left", padx=(4, 0))
        ttk.Button(bar, text="刷新财报", command=self._refresh_finance_tab, width=12).pack(side="right")

        body = ttk.Frame(self.tab_finance)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=3)
        body.rowconfigure(1, weight=2)
        body.rowconfigure(2, weight=1)

        daily_box = ttk.LabelFrame(body, text="每日营收（近14天）", padding=4)
        daily_box.grid(row=0, column=0, sticky="nsew", padx=(0, 4), pady=(0, 4))
        self.fin_daily_tree = self._build_tree(
            daily_box, (("date", "日期", 80, "center"), ("revenue", "营收", 85, "e"),
                        ("cost", "成本", 70, "e"), ("profit", "毛利", 85, "e"),
                        ("margin", "毛利率", 60, "e"), ("orders", "单数", 40, "center")), height=8)
        self.fin_daily_tree.pack(fill="both", expand=True)

        monthly_box = ttk.LabelFrame(body, text="每月营收（近12月）", padding=4)
        monthly_box.grid(row=1, column=0, sticky="nsew", padx=(0, 4), pady=(0, 4))
        self.fin_monthly_tree = self._build_tree(
            monthly_box, (("period", "月份", 80, "center"), ("revenue", "营收", 85, "e"),
                          ("cost", "成本", 70, "e"), ("profit", "毛利", 85, "e"),
                          ("margin", "毛利率", 60, "e"), ("orders", "单数", 40, "center")), height=6)
        self.fin_monthly_tree.pack(fill="both", expand=True)

        yearly_box = ttk.LabelFrame(body, text="每年营收", padding=4)
        yearly_box.grid(row=2, column=0, sticky="nsew", padx=(0, 4))
        self.fin_yearly_tree = self._build_tree(
            yearly_box, (("period", "年份", 80, "center"), ("revenue", "营收", 85, "e"),
                         ("cost", "成本", 70, "e"), ("profit", "毛利", 85, "e"),
                         ("margin", "毛利率", 60, "e"), ("orders", "单数", 40, "center")), height=4)
        self.fin_yearly_tree.pack(fill="both", expand=True)

        # 右列
        # 畅销排行（销量）
        top_qty_box = ttk.LabelFrame(body, text="畅销排行（销量 TOP10）", padding=4)
        top_qty_box.grid(row=0, column=1, sticky="nsew", padx=(4, 0), pady=(0, 4))
        self.fin_top_qty_tree = self._build_tree(
            top_qty_box, (("name", "商品", 100, "w"), ("category", "类别", 50, "center"),
                          ("total_qty", "销量", 50, "e"), ("total_revenue", "销售额", 65, "e")), height=5)
        self.fin_top_qty_tree.pack(fill="both", expand=True)

        # 畅销排行（金额）
        top_rev_box = ttk.LabelFrame(body, text="畅销排行（销售额 TOP10）", padding=4)
        top_rev_box.grid(row=1, column=1, sticky="nsew", padx=(4, 0), pady=(0, 4))
        self.fin_top_rev_tree = self._build_tree(
            top_rev_box, (("name", "商品", 100, "w"), ("category", "类别", 50, "center"),
                          ("total_qty", "销量", 50, "e"), ("total_revenue", "销售额", 65, "e")), height=5)
        self.fin_top_rev_tree.pack(fill="both", expand=True)

        # 入库建议（可调天数）+ 库存警告，并排
        bottom_frame = ttk.Frame(body)
        bottom_frame.grid(row=2, column=1, sticky="nsew", padx=(4, 0))
        bottom_frame.columnconfigure(0, weight=1)
        bottom_frame.columnconfigure(1, weight=1)

        reorder_box = ttk.LabelFrame(bottom_frame, text="入库建议", padding=4)
        reorder_box.grid(row=0, column=0, sticky="nsew", padx=(0, 2))
        reorder_bar = ttk.Frame(reorder_box)
        reorder_bar.pack(fill="x", pady=(0, 2))
        ttk.Label(reorder_bar, text="基于近").pack(side="left")
        self.fin_reorder_days_var = tk.StringVar(value="7")
        self.fin_reorder_days_combo = ttk.Combobox(reorder_bar, textvariable=self.fin_reorder_days_var,
                                                    width=4, state="readonly", font=(UI_FONT, 10))
        self.fin_reorder_days_combo["values"] = ["7", "14", "30", "60", "90"]
        self.fin_reorder_days_combo.pack(side="left", padx=2)
        ttk.Label(reorder_bar, text="天销量").pack(side="left")
        ttk.Button(reorder_bar, text="刷新", command=self._refresh_reorder, width=5).pack(side="right")
        self.fin_reorder_tree = self._build_tree(
            reorder_box, (("name", "商品", 80, "w"), ("stock", "库存", 35, "e"),
                          ("avg", "日均", 35, "e"), ("suggest", "建议入库", 55, "e")), height=5)
        self.fin_reorder_tree.pack(fill="both", expand=True)

        warn_box = ttk.LabelFrame(bottom_frame, text="库存警告", padding=4)
        warn_box.grid(row=0, column=1, sticky="nsew", padx=(2, 0))
        self.fin_warn_tree = self._build_tree(
            warn_box, (("name", "商品", 90, "w"), ("stock", "库存", 35, "e"),
                       ("low", "预警线", 35, "e")), height=5)
        self.fin_warn_tree.pack(fill="both", expand=True)
        self.fin_warn_tree.tag_configure("low", foreground="red")

    def _refresh_finance_tab(self) -> None:
        try:
            rep = self.db.finance_report()
        except Exception:
            logger.exception("财报查询失败")
            return

        cards = rep["cards"]
        for key, (rev, profit, margin, cost, orders) in cards.items():
            self.fin_cards[key].set(
                f"营收: ¥{rev:.2f}\n毛利: ¥{profit:.2f}\n毛利率: {margin}\n成本: ¥{cost:.2f}\n单数: {orders}"
            )

        self.fin_cards["inventory"].set(
            f"¥{rep['inventory_value']:,.2f}")

        def period_rows(data):
            return [((d["period"], f"{d['revenue']:.2f}", f"{d['cost']:.2f}",
                      f"{d['profit']:.2f}", d["margin"], d["orders"]),
                     d["period"], ()) for d in data]

        self._fill_tree(self.fin_daily_tree, period_rows(rep["daily"]))
        self._fill_tree(self.fin_monthly_tree, period_rows(rep["monthly"]))
        self._fill_tree(self.fin_yearly_tree, period_rows(rep["yearly"]))

        # 畅销排行
        def top_rows(data):
            return [((d["name"], d.get("category", ""), d["total_qty"],
                      f"{d['total_revenue']:.2f}"),
                     str(d["product_id"]), ()) for d in data]
        self._fill_tree(self.fin_top_qty_tree, top_rows(rep["top_by_qty"]))
        self._fill_tree(self.fin_top_rev_tree, top_rows(rep["top_by_rev"]))

        warn_rows = [((w["name"], w["stock"], w["low_stock"]), str(w["id"]), ("low",))
                     for w in rep["warnings"]]
        self._fill_tree(self.fin_warn_tree, warn_rows)
        self.fin_warn_tree.tag_configure("low", foreground="red")

        reorder_rows = [((r["name"], r["stock"], r["daily_avg"], r["suggest"]),
                         str(r["id"]), ()) for r in rep["reorder"]]
        self._fill_tree(self.fin_reorder_tree, reorder_rows)

    def _refresh_reorder(self) -> None:
        """按自定义天数刷新入库建议。"""
        try:
            days = int(self.fin_reorder_days_var.get())
        except ValueError:
            days = 7
        try:
            rep = self.db.finance_report(reorder_days=days)
        except Exception:
            logger.exception("入库建议查询失败")
            return
        reorder_rows = [((r["name"], r["stock"], r["daily_avg"], r["suggest"]),
                         str(r["id"]), ()) for r in rep["reorder"]]
        self._fill_tree(self.fin_reorder_tree, reorder_rows)

    def _refresh_finance_range(self) -> None:
        """查询自定义日期范围的营收，结果显示在每日营收区。"""
        start = self.fin_range_start.get().strip()
        end = self.fin_range_end.get().strip()
        if not start or not end:
            messagebox.showwarning("提示", "请输入起始日期和结束日期（格式: YYYY-MM-DD）")
            return
        self._do_finance_range_query(start, end)

    def _on_fin_range_select(self, _event=None) -> None:
        """下拉选择预设日期范围时自动查询。"""
        choice = self.fin_range_var.get()
        if choice == "自定义...":
            self.fin_custom_frame.pack(side="left", before=self.fin_range_combo)
            return
        self.fin_custom_frame.pack_forget()
        today = datetime.date.today()
        mapping = {
            "今天": (today, today),
            "昨天": (today - datetime.timedelta(days=1), today - datetime.timedelta(days=1)),
            "本周": (today - datetime.timedelta(days=today.weekday()), today),
            "上周": (today - datetime.timedelta(days=today.weekday() + 7),
                     today - datetime.timedelta(days=today.weekday() + 1)),
            "本月": (today.replace(day=1), today),
            "上月": ((today.replace(day=1) - datetime.timedelta(days=1)).replace(day=1),
                     today.replace(day=1) - datetime.timedelta(days=1)),
            "近7天": (today - datetime.timedelta(days=6), today),
            "近30天": (today - datetime.timedelta(days=29), today),
            "本季度": (
                today.replace(month=(today.month - 1) // 3 * 3 + 1, day=1),
                today,
            ),
            "本年": (today.replace(month=1, day=1), today),
        }
        if choice in mapping:
            start, end = mapping[choice]
            self._do_finance_range_query(start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))

    def _do_finance_range_query(self, start: str, end: str) -> None:
        try:
            rep = self.db.finance_range(start, end)
        except Exception:
            logger.exception("自定义日期查询失败")
            messagebox.showerror("查询失败", "详见 cashier.log")
            return

        if not rep["daily"]:
            messagebox.showinfo("查询结果", f"{start} — {end} 期间无销售记录")
            self._fill_tree(self.fin_daily_tree, [])
            return

        rows = [((d["period"], f"{d['revenue']:.2f}", f"{d['cost']:.2f}",
                  f"{d['profit']:.2f}", d["margin"], d["orders"]),
                 d["period"], ()) for d in rep["daily"]]
        self._fill_tree(self.fin_daily_tree, rows)

        msg = (
            f"📅 {start} — {end}\n\n"
            f"营收: ¥{rep['total_revenue']:,.2f}\n"
            f"成本: ¥{rep['total_cost']:,.2f}\n"
            f"毛利: ¥{rep['total_profit']:,.2f}\n"
            f"毛利率: {rep['total_margin']}\n"
            f"单数: {rep['total_orders']}"
        )
        messagebox.showinfo("查询汇总", msg)

    # ------------------------------------------------------------------ #
    # 数据备份
    # ------------------------------------------------------------------ #
    def _build_backup_tab(self) -> None:
        outer = ttk.Frame(self.tab_backup)
        outer.pack(fill="both", expand=True, padx=10, pady=10)

        sb = ttk.Scrollbar(outer, orient="vertical")
        canvas = tk.Canvas(outer, yscrollcommand=sb.set, highlightthickness=0)
        sb.config(command=canvas.yview)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        box = ttk.Frame(canvas)
        canvas.create_window((0, 0), window=box, anchor="nw", tags="container")

        # ========================
        # Section 1 — 数据备份
        # ========================
        s1 = ttk.LabelFrame(box, text="💾 数据备份（商品 + 销售 + 会员 + 数据库 → ZIP）", padding=12)
        s1.pack(fill="x", pady=(0, 8))

        ttk.Label(s1, text=f"数据库: {DB_PATH}", foreground="gray").pack(anchor="w")
        ttk.Label(s1, text=f"备份目录: {BACKUP_DIR}", foreground="gray").pack(anchor="w")

        row1 = ttk.Frame(s1)
        row1.pack(fill="x", pady=(8, 4))
        ttk.Button(row1, text="📦 一键备份（商品+销售+会员+数据库 → ZIP）",
                   command=self._run_daily_backup_manual, width=42).pack(side="left")
        ttk.Button(row1, text="📥 从备份恢复",
                   command=self._restore_db, width=18).pack(side="left", padx=(8, 0))

        # 每日备份状态
        daily = ttk.LabelFrame(s1, text="每日自动备份", padding=6)
        daily.pack(fill="x", pady=(8, 0))
        ttk.Label(daily, text=f"目录: {DAILY_BACKUP_DIR}", foreground="gray").pack(anchor="w")
        self.daily_status_var = tk.StringVar(value="检查中...")
        ttk.Label(daily, textvariable=self.daily_status_var, foreground="#d33").pack(anchor="w", pady=(2, 0))

        # ========================
        # Section 2 — 数据导入
        # ========================
        s2 = ttk.LabelFrame(box, text="📥 数据导入（从 Excel 恢复数据）", padding=12)
        s2.pack(fill="x", pady=(0, 8))
        ttk.Label(s2, text="先下载模板 → 按格式填写 → 导入对应数据",
                  foreground="gray").pack(anchor="w", pady=(0, 6))

        trow = ttk.Frame(s2)
        trow.pack(fill="x", pady=2)
        ttk.Label(trow, text="下载模板:", width=10).pack(side="left")
        ttk.Button(trow, text="商品模板", command=self._download_product_template, width=12).pack(side="left", padx=2)
        ttk.Button(trow, text="销售模板", command=self._download_sales_template, width=12).pack(side="left", padx=2)
        ttk.Button(trow, text="会员模板", command=self._download_member_template, width=12).pack(side="left", padx=2)
        ttk.Button(trow, text="一键全部模板", command=self._download_all_template, width=16).pack(side="left", padx=(8, 0))

        irow = ttk.Frame(s2)
        irow.pack(fill="x", pady=(4, 0))
        ttk.Label(irow, text="导入数据:", width=10).pack(side="left")
        ttk.Button(irow, text="导入商品 Excel", command=self._import_products, width=16).pack(side="left", padx=2)
        ttk.Button(irow, text="导入销售 Excel", command=self._import_sales_ui, width=16).pack(side="left", padx=2)
        ttk.Button(irow, text="导入会员 Excel", command=self._import_members, width=16).pack(side="left", padx=2)

        # ========================
        # Section 3 — 重置
        # ========================
        s3 = ttk.LabelFrame(box, text="🔄 重置数据", padding=12)
        s3.pack(fill="x")
        row3 = ttk.Frame(s3)
        row3.pack(fill="x")
        ttk.Button(row3, text="重置软件数据", command=self._reset_all_data_ui, width=18).pack(side="left")
        ttk.Label(row3, text="重置前自动备份，备份失败不清除数据",
                  foreground="#d33").pack(side="left", padx=(8, 0))

        # ========================
        # Section 4 — 数据导出
        # ========================
        s4 = ttk.LabelFrame(box, text="📤 数据导出", padding=12)
        s4.pack(fill="x", pady=(8, 0))

        erow1 = ttk.Frame(s4)
        erow1.pack(fill="x", pady=2)
        ttk.Label(erow1, text="CSV:", width=6).pack(side="left")
        ttk.Button(erow1, text="商品", command=self._export_products, width=8).pack(side="left", padx=2)
        ttk.Button(erow1, text="销售", command=self._export_sales, width=8).pack(side="left", padx=2)
        ttk.Button(erow1, text="会员", command=self._export_members_csv, width=8).pack(side="left", padx=2)
        ttk.Button(erow1, text="库存", command=self._export_stock_csv, width=8).pack(side="left", padx=2)
        ttk.Button(erow1, text="库存日志", command=self._export_stock_logs_csv, width=10).pack(side="left", padx=2)

        erow2 = ttk.Frame(s4)
        erow2.pack(fill="x", pady=(2, 0))
        ttk.Label(erow2, text="Excel:", width=6).pack(side="left")
        ttk.Button(erow2, text="商品", command=self._export_products_excel, width=8).pack(side="left", padx=2)
        ttk.Button(erow2, text="销售", command=self._export_sales_excel, width=8).pack(side="left", padx=2)
        ttk.Button(erow2, text="会员", command=self._export_members_excel, width=8).pack(side="left", padx=2)
        ttk.Button(erow2, text="库存日志", command=self._export_stock_logs_excel, width=10).pack(side="left", padx=2)
        ttk.Button(erow2, text="一键全部", command=self._export_all_excel, width=10).pack(side="left", padx=(6, 2))

        # scrollbar config
        def _resize(_event=None):
            box.update_idletasks()
            canvas.config(scrollregion=canvas.bbox("all"))
            canvas.itemconfig("container", width=canvas.winfo_width())
        box.bind("<Configure>", _resize, add="+")
        canvas.bind("<Configure>", _resize, add="+")
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

    # ------------------------------------------------------------------ #
    # 扫码枪
    # ------------------------------------------------------------------ #
    def _on_barcode_raw(self, code: str) -> None:
        try:
            self._barcode_queue.put(code, block=False)
        except queue.Full:
            pass

    def _poll_barcode(self) -> None:
        try:
            while True:
                code = self._barcode_queue.get_nowait()
                self._handle_barcode(code)
        except queue.Empty:
            pass
        self.after(80, self._poll_barcode)

    def _fuzzy_barcode_search(self, query: str) -> List[Tuple[float, Dict[str, Any]]]:
        """条码模糊搜索。返回 [(score, product), ...] 按 score 降序排列。
        score 基于连续匹配子串长度 / 最大长度。精确匹配 score=1.0。"""
        if not query.strip():
            return []
        q = query.strip()
        try:
            products = self.db.search_products("")
        except Exception:
            return []
        results = []
        for p in products:
            bc = (p.get("barcode") or "").strip()
            if not bc:
                continue
            if bc == q:
                results.append((1.0, p))
                continue
            # 连续最长公共子串
            lcs = 0
            for i in range(len(bc)):
                for j in range(len(q)):
                    k = 0
                    while i + k < len(bc) and j + k < len(q) and bc[i + k] == q[j + k]:
                        k += 1
                    lcs = max(lcs, k)
            if lcs >= 3:
                score = lcs / max(len(bc), len(q))
                results.append((score, p))
            elif q in bc:
                results.append((len(q) / len(bc), p))
        results.sort(key=lambda x: x[0], reverse=True)
        return results

    def _show_barcode_search_popup(self, query: str, results: List[Tuple[float, Dict[str, Any]]],
                                    on_select: callable) -> None:
        """弹出条码模糊搜索候选窗口。on_select(product) 在用户选中时回调。"""
        win = tk.Toplevel(self)
        win.title(f"条码搜索: {query}")
        win.transient(self)
        win.grab_set()
        win.resizable(False, False)

        frm = ttk.Frame(win, padding=12)
        frm.pack(fill="both", expand=True)

        if not results:
            ttk.Label(frm, text=f"未找到匹配「{query}」的商品", font=(UI_FONT, 12),
                      foreground="gray").pack(padx=30, pady=20)
            ttk.Button(frm, text="关闭", command=win.destroy, width=12).pack()
            win.update_idletasks()
            x = self.winfo_x() + (self.winfo_width() - win.winfo_width()) // 2
            y = self.winfo_y() + (self.winfo_height() - win.winfo_height()) // 2
            win.geometry(f"+{x}+{y}")
            return

        ttk.Label(frm, text=f"找到 {len(results)} 个候选商品（按匹配度排序）:", font=(UI_FONT, 11)).pack(anchor="w")

        tree = ttk.Treeview(frm, columns=("barcode", "name", "score"), show="headings",
                            height=min(len(results), 10))
        for cid, text, w, a in [("barcode", "条码", 130, "center"),
                                 ("name", "商品名称", 180, "w"),
                                 ("score", "匹配度", 60, "center")]:
            tree.heading(cid, text=text)
            tree.column(cid, width=w, anchor=a)
        tree.pack(fill="both", expand=True, pady=(4, 8))

        for score, p in results:
            tree.insert("", "end", values=(p.get("barcode", ""), p["name"], f"{score:.0%}"))

        def _select():
            sel = tree.selection()
            if not sel:
                return
            idx = tree.index(sel[0])
            if 0 <= idx < len(results):
                win.destroy()
                on_select(results[idx][1])

        tree.bind("<Double-1>", lambda _: _select())
        ttk.Button(frm, text="选择", command=_select, width=14).pack()

        win.bind("<Return>", lambda _: _select())
        win.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - win.winfo_width()) // 2
        y = self.winfo_y() + (self.winfo_height() - win.winfo_height()) // 2
        win.geometry(f"+{x}+{y}")

    def _handle_barcode(self, code: str) -> None:
        index = self.notebook.index(self.notebook.select())
        if index == 0:
            try:
                products = self.db.get_products_by_barcode(code)
                if products:
                    if len(products) == 1:
                        self._add_to_cart(products[0])
                        self._set_status(f"扫码: {products[0]['name']}", "green")
                    else:
                        self._show_barcode_search_popup(
                            code, [(1.0, p) for p in products],
                            lambda p: (self._add_to_cart(p), self._set_status(f"扫码: {p['name']}", "green"))
                        )
                    self.cashier_search_var.set("")
                else:
                    results = self._fuzzy_barcode_search(code)
                    if len(results) == 1 and results[0][0] >= 0.9:
                        self._add_to_cart(results[0][1])
                        self._set_status(f"扫码(模糊): {results[0][1]['name']}", "green")
                    elif results:
                        self._show_barcode_search_popup(
                            code, results,
                            lambda p: (self._add_to_cart(p), self._set_status(f"扫码: {p['name']}", "green"))
                        )
                    else:
                        self._set_status(f"未找到条码: {code}", "red")
            except Exception:
                pass
        elif index == 3:
            try:
                products = self.db.get_products_by_barcode(code)
                if products:
                    if len(products) == 1:
                        self._stock_select_and_refresh(products[0])
                    else:
                        self._show_barcode_search_popup(
                            code, [(1.0, p) for p in products],
                            self._stock_select_and_refresh)
                else:
                    results = self._fuzzy_barcode_search(code)
                    if len(results) == 1 and results[0][0] >= 0.9:
                        self._stock_select_and_refresh(results[0][1])
                        self._set_status(f"扫码(模糊): {results[0][1]['name']}", "green")
                    elif results:
                        self._show_barcode_search_popup(code, results, self._stock_select_and_refresh)
                    else:
                        self._set_status(f"未找到条码: {code}", "red")
            except Exception:
                pass
        else:
            self._set_status(f"扫码: {code}（当前页面不支持）", "gray")

    def _set_status(self, text: str, color: str = "green") -> None:
        self.status_var.set(text)
        if self.status_label:
            self.status_label.configure(foreground=color)
        try:
            if color == "green":
                winsound.Beep(1000, 50)
            elif color == "red":
                winsound.Beep(300, 120)
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # 每日备份
    # ------------------------------------------------------------------ #
    def _check_daily_backup(self) -> None:
        self._refresh_daily_status()
        if not self._today_backup_done():
            self._run_daily_backup(manual=False)
        try:
            self.db.cleanup_old_backups(DAILY_BACKUP_DIR)
        except Exception:
            logger.exception("清理旧备份失败")
        self.after(30 * 60 * 1000, self._check_daily_backup)

    def _today_backup_done(self) -> bool:
        day = datetime.datetime.now().strftime("%Y-%m-%d")
        day_dir = os.path.join(DAILY_BACKUP_DIR, day)
        try:
            if not os.path.isdir(day_dir):
                return False
            return any(f.endswith(".zip") for f in os.listdir(day_dir))
        except OSError:
            return False

    def _refresh_daily_status(self) -> None:
        if self._today_backup_done():
            self.daily_status_var.set("今日已自动备份 ✅")
        else:
            self.daily_status_var.set("今日尚未备份（程序启动后将自动执行）")

    def _run_daily_backup(self, manual: bool = True) -> None:
        try:
            result = self.db.daily_backup_zip(DAILY_BACKUP_DIR)
        except Exception:
            logger.exception("每日备份失败")
            self.daily_status_var.set("每日备份失败")
            self._set_status("每日备份失败", "red")
            if manual:
                messagebox.showerror("备份失败", "详见 cashier.log")
            return
        self.daily_status_var.set(f"今日已备份（{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）")
        self._set_status("每日备份完成: 全部数据打包为 ZIP", "green")
        if manual:
            messagebox.showinfo("每日备份完成",
                                f"已打包全部数据为 ZIP:\n\n{result}\n\n包含: 数据库 + 商品 + 销售（CSV & Excel）")

    def _run_daily_backup_manual(self) -> None:
        self._run_daily_backup(manual=True)

    # 备份导出回调
    def _do_backup(self) -> None:
        try:
            path = self.db.backup(BACKUP_DIR)
        except Exception:
            messagebox.showerror("备份失败", "发生未知错误")
            return
        messagebox.showinfo("备份成功", f"数据库已备份到:\n{path}")

    def _reset_all_data_ui(self) -> None:
        """强制备份成功并经二次确认后清空全部业务数据。"""
        if not messagebox.askyesno(
            "重置软件数据",
            "此操作将清空商品、会员、库存、销售和操作日志。\n\n"
            "系统会先强制保存数据库和全部导出数据，备份失败时不会清除。\n\n是否继续？",
            icon="warning",
        ):
            return
        try:
            backup_path = self.db.daily_backup_zip(DAILY_BACKUP_DIR)
            if not os.path.isfile(backup_path) or os.path.getsize(backup_path) <= 0:
                raise OSError("备份文件未成功生成")
        except Exception:
            logger.exception("重置前强制备份失败")
            messagebox.showerror("禁止重置", "数据库和全部数据备份失败，未清除任何数据。\n详见 cashier.log")
            return
        if not messagebox.askyesno(
            "最终确认",
            f"强制备份已完成：\n{backup_path}\n\n"
            "确认立即清空当前软件全部业务数据？此操作不可撤回。",
            icon="warning",
        ):
            messagebox.showinfo("已取消", f"未清除任何数据。\n备份保留在：\n{backup_path}")
            return
        try:
            self.db.reset_all_data()
            self.cart.clear()
            self._deactivate_member()
            self._refresh_all_first()
            self._refresh_cart()
            self._refresh_daily_status()
        except Exception:
            logger.exception("重置软件数据失败")
            messagebox.showerror("重置失败", f"数据未能清空。可使用以下备份恢复：\n{backup_path}")
            return
        self._set_status("软件数据已重置", "green")
        messagebox.showinfo("重置完成", f"当前软件数据已清空。\n\n强制备份保留在：\n{backup_path}")

    def _export_products(self) -> None:
        path = filedialog.asksaveasfilename(title="导出商品", defaultextension=".csv", initialdir=BACKUP_DIR,
                                            initialfile="products.csv", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        try:
            n = self.db.export_products_csv(path)
        except Exception:
            messagebox.showerror("导出失败", "详见 cashier.log")
            return
        messagebox.showinfo("成功", f"已导出 {n} 条商品")

    def _export_sales(self) -> None:
        path = filedialog.asksaveasfilename(title="导出销售", defaultextension=".csv", initialdir=BACKUP_DIR,
                                            initialfile="sales.csv", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        try:
            n = self.db.export_sales_csv(path)
        except Exception:
            messagebox.showerror("导出失败", "详见 cashier.log")
            return
        messagebox.showinfo("成功", f"已导出 {n} 条销售单")

    def _export_products_excel(self) -> None:
        path = filedialog.asksaveasfilename(title="导出商品 Excel", defaultextension=".xlsx", initialdir=BACKUP_DIR,
                                            initialfile="商品清单.xlsx", filetypes=[("Excel", "*.xlsx")])
        if not path:
            return
        try:
            n = self.db.export_products_excel(path)
        except Exception:
            logger.exception("导出商品Excel失败")
            messagebox.showerror("导出失败", "详见 cashier.log")
            return
        messagebox.showinfo("成功", f"已导出 {n} 条商品")

    def _export_sales_excel(self) -> None:
        path = filedialog.asksaveasfilename(title="导出销售 Excel", defaultextension=".xlsx", initialdir=BACKUP_DIR,
                                            initialfile="销售记录.xlsx", filetypes=[("Excel", "*.xlsx")])
        if not path:
            return
        try:
            n = self.db.export_sales_excel(path)
        except Exception:
            logger.exception("导出销售Excel失败")
            messagebox.showerror("导出失败", "详见 cashier.log")
            return
        messagebox.showinfo("成功", f"已导出 {n} 条销售单")

    def _export_members_csv(self) -> None:
        path = filedialog.asksaveasfilename(title="导出会员 CSV", defaultextension=".csv", initialdir=BACKUP_DIR,
                                            initialfile="会员清单.csv", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        try:
            n = self.db.export_members_csv(path)
        except Exception:
            logger.exception("导出会员CSV失败")
            messagebox.showerror("导出失败", "详见 cashier.log")
            return
        messagebox.showinfo("成功", f"已导出 {n} 条会员")

    def _export_members_excel(self) -> None:
        path = filedialog.asksaveasfilename(title="导出会员 Excel", defaultextension=".xlsx", initialdir=BACKUP_DIR,
                                            initialfile="会员清单.xlsx", filetypes=[("Excel", "*.xlsx")])
        if not path:
            return
        try:
            n = self.db.export_members_excel(path)
        except Exception:
            logger.exception("导出会员Excel失败")
            messagebox.showerror("导出失败", "详见 cashier.log")
            return
        messagebox.showinfo("成功", f"已导出 {n} 条会员")

    def _export_stock_csv(self) -> None:
        path = filedialog.asksaveasfilename(title="导出库存 CSV", defaultextension=".csv", initialdir=BACKUP_DIR,
                                            initialfile="库存快照.csv", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        try:
            n = self.db.export_stock_csv(path)
        except Exception:
            logger.exception("导出库存CSV失败")
            messagebox.showerror("导出失败", "详见 cashier.log")
            return
        messagebox.showinfo("成功", f"已导出 {n} 条库存记录")

    def _export_all_excel(self) -> None:
        path = filedialog.asksaveasfilename(title="一键导出全部数据", defaultextension=".xlsx", initialdir=BACKUP_DIR,
                                            initialfile="全部数据.xlsx", filetypes=[("Excel", "*.xlsx")])
        if not path:
            return
        try:
            n = self.db.export_all_excel(path)
        except Exception:
            logger.exception("一键导出失败")
            messagebox.showerror("导出失败", "详见 cashier.log")
            return
        messagebox.showinfo("成功", f"已导出商品+会员+销售+库存共 {n} 条到\n{path}")

    def _export_stock_logs_csv(self) -> None:
        path = filedialog.asksaveasfilename(title="导出库存日志 CSV", defaultextension=".csv", initialdir=BACKUP_DIR,
                                            initialfile="库存日志.csv", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        try:
            n = self.db.export_stock_logs_csv(path)
        except Exception:
            logger.exception("导出库存日志CSV失败")
            messagebox.showerror("导出失败", "详见 cashier.log")
            return
        messagebox.showinfo("成功", f"已导出 {n} 条库存日志")

    def _export_stock_logs_excel(self) -> None:
        path = filedialog.asksaveasfilename(title="导出库存日志 Excel", defaultextension=".xlsx", initialdir=BACKUP_DIR,
                                            initialfile="库存日志.xlsx", filetypes=[("Excel", "*.xlsx")])
        if not path:
            return
        try:
            n = self.db.export_stock_logs_excel(path)
        except Exception:
            logger.exception("导出库存日志Excel失败")
            messagebox.showerror("导出失败", "详见 cashier.log")
            return
        messagebox.showinfo("成功", f"已导出 {n} 条库存日志")

    def _download_sales_template(self) -> None:
        path = filedialog.asksaveasfilename(title="保存销售导入模板", defaultextension=".xlsx", initialdir=BACKUP_DIR,
                                            initialfile="销售导入模板.xlsx", filetypes=[("Excel", "*.xlsx")])
        if not path:
            return
        self.db.write_sales_template(path)
        messagebox.showinfo("成功", f"模板已导出:\n{path}")

    def _download_all_template(self) -> None:
        path = filedialog.asksaveasfilename(title="保存全部模板", defaultextension=".xlsx",
                                            initialfile="全部导入模板.xlsx", filetypes=[("Excel", "*.xlsx")])
        if not path:
            return
        self.db.write_all_template(path)
        messagebox.showinfo("成功", f"全部模板（商品+会员+库存+销售）已导出:\n{path}")

    def _import_sales_ui(self) -> None:
        path = filedialog.askopenfilename(title="选择销售导入文件", initialdir=BACKUP_DIR,
                                          filetypes=[("Excel/CSV", "*.xlsx;*.csv"), ("Excel", "*.xlsx"), ("CSV", "*.csv")])
        if not path:
            return
        try:
            rows = self.db.parse_sales_import(path)
        except DatabaseError as exc:
            messagebox.showerror("导入失败", str(exc))
            return
        if not rows:
            messagebox.showwarning("提示", "文件中没有可导入数据")
            return
        if not messagebox.askyesno("确认导入", f"将从文件导入 {len(rows)} 行销售数据。\n已存在的销售单号将被跳过。确定继续？"):
            return
        try:
            result = self.db.import_sales(rows)
        except Exception:
            logger.exception("导入销售失败")
            messagebox.showerror("导入失败", "详见 cashier.log")
            return
        messagebox.showinfo("导入完成", f"新增 {result['inserted']} 笔销售单，跳过 {result['skipped']} 行")
        self._refresh_sales_tab()
        self._refresh_stock_tab()

    def _download_product_template(self) -> None:
        path = filedialog.asksaveasfilename(title="保存商品模板", defaultextension=".xlsx", initialdir=BACKUP_DIR,
                                            initialfile="商品导入模板.xlsx", filetypes=[("Excel", "*.xlsx")])
        if not path:
            return
        self.db.write_product_template(path)
        messagebox.showinfo("成功", f"模板已导出:\n{path}")

    def _download_member_template(self) -> None:
        path = filedialog.asksaveasfilename(title="保存会员模板", defaultextension=".xlsx", initialdir=BACKUP_DIR,
                                            initialfile="会员导入模板.xlsx", filetypes=[("Excel", "*.xlsx")])
        if not path:
            return
        self.db.write_member_template(path)
        messagebox.showinfo("成功", f"模板已导出:\n{path}")

    def _download_stock_template(self) -> None:
        path = filedialog.asksaveasfilename(title="保存库存调整模板", defaultextension=".xlsx", initialdir=BACKUP_DIR,
                                            initialfile="库存调整模板.xlsx", filetypes=[("Excel", "*.xlsx")])
        if not path:
            return
        self.db.write_stock_template(path)
        messagebox.showinfo("成功", f"模板已导出:\n{path}")

    def _import_products(self) -> None:
        path = filedialog.askopenfilename(title="选择商品导入文件", initialdir=BACKUP_DIR,
                                          filetypes=[("Excel/CSV", "*.xlsx;*.csv"), ("Excel", "*.xlsx"), ("CSV", "*.csv")])
        if not path:
            return
        try:
            rows = self.db.parse_product_import(path)
        except DatabaseError as exc:
            messagebox.showerror("导入失败", str(exc))
            return
        if not rows:
            messagebox.showwarning("提示", "文件中没有可导入数据")
            return
        if not messagebox.askyesno("确认导入", f"将从文件导入 {len(rows)} 行商品数据。确定继续？"):
            return
        try:
            result = self.db.import_products(rows)
        except Exception:
            logger.exception("商品导入失败")
            messagebox.showerror("导入失败", "详见 cashier.log")
            return
        messagebox.showinfo("导入完成", f"新增 {result['inserted']} 条，更新 {result['updated']} 条，跳过 {result['skipped']} 条")
        self._refresh_product_related_views()

    def _import_members(self) -> None:
        path = filedialog.askopenfilename(title="选择会员导入文件", initialdir=BACKUP_DIR,
                                          filetypes=[("Excel/CSV", "*.xlsx;*.csv"), ("Excel", "*.xlsx"), ("CSV", "*.csv")])
        if not path:
            return
        try:
            rows = self.db.parse_member_import(path)
        except DatabaseError as exc:
            messagebox.showerror("导入失败", str(exc))
            return
        if not rows:
            messagebox.showwarning("提示", "文件中没有可导入数据")
            return
        if not messagebox.askyesno("确认导入", f"将从文件导入 {len(rows)} 行会员数据。\n规则：手机号已存在或格式错误跳过。确定继续？"):
            return
        try:
            result = self.db.import_members(rows)
        except Exception:
            messagebox.showerror("导入失败", "详见 cashier.log")
            return
        messagebox.showinfo("导入完成", f"新增 {result['inserted']} 条，跳过 {result['skipped']} 条")
        self._refresh_members_tab()

    def _import_stock_ui(self) -> None:
        path = filedialog.askopenfilename(title="选择库存调整导入文件", initialdir=BACKUP_DIR,
                                          filetypes=[("Excel/CSV", "*.xlsx;*.csv"), ("Excel", "*.xlsx"), ("CSV", "*.csv")])
        if not path:
            return
        try:
            rows = self.db.parse_stock_import(path)
        except DatabaseError as exc:
            messagebox.showerror("导入失败", str(exc))
            return
        if not rows:
            messagebox.showwarning("提示", "文件中没有可导入数据")
            return
        if not messagebox.askyesno("确认导入", f"将从文件调整 {len(rows)} 条库存。按条码/名称匹配商品。确定继续？"):
            return
        try:
            result = self.db.import_stock(rows)
        except Exception:
            messagebox.showerror("导入失败", "详见 cashier.log")
            return
        messagebox.showinfo("导入完成", f"库存已调整 {result['updated']} 条，跳过 {result['skipped']} 条")
        self._refresh_stock_tab()

    def _restore_db(self) -> None:
        path = filedialog.askopenfilename(title="选择备份包（.zip）", initialdir=BACKUP_DIR,
                                          filetypes=[("ZIP 备份包", "*.zip"), ("所有文件", "*.*")])
        if not path:
            return
        if not messagebox.askyesno("⚠ 确认恢复",
                                   f"将解压以下备份包并覆盖当前所有数据：\n\n{path}\n\n"
                                   f"当前数据将先打包备份到:\n{BACKUP_DIR}\n"
                                   f"文件名为「恢复前备份_时间戳.zip」。\n\n"
                                   f"程序将自动重启完成恢复。\n\n确定继续？",
                                   icon="warning"):
            return
        import subprocess
        try:
            bat = self.db.prepare_restore(path)
        except DatabaseError as exc:
            messagebox.showerror("恢复失败", str(exc))
            return
        try:
            if self._scanner:
                self._scanner.stop()
        except Exception:
            pass
        self.destroy()
        self.quit()
        subprocess.Popen(["cmd", "/c", bat], creationflags=0x00000008)

    # ------------------------------------------------------------------ #
    # 汇总刷新 & 退出
    # ------------------------------------------------------------------ #
    def _refresh_all_first(self) -> None:
        self._refresh_product_list()
        self._refresh_products_tab()
        self._refresh_members_tab()
        self._refresh_stock_tab()
        self._refresh_sales_tab()
        self._refresh_finance_tab()

    def _on_tab_changed(self, _event=None) -> None:
        idx = self.notebook.index(self.notebook.select())
        if idx == 0:
            self._refresh_product_list()
        elif idx == 1:
            self._refresh_products_tab()
        elif idx == 2:
            self._refresh_members_tab()
        elif idx == 3:
            self._refresh_stock_tab()
        elif idx == 4:
            self._refresh_sales_tab()
        elif idx == 6:
            self._refresh_finance_tab()

    def _on_close(self) -> None:
        """窗口关闭前：自动备份数据库，再停止扫码枪并释放资源。"""
        try:
            self.db.daily_backup_zip(DAILY_BACKUP_DIR)
            self._set_status("关闭前自动备份完成", "green")
        except Exception:
            logger.exception("关闭前自动备份失败")
        try:
            if self._scanner:
                self._scanner.stop()
        except Exception:
            logger.exception("停止扫码枪失败")
        try:
            self.db._connect().close()
        except Exception:
            logger.exception("清理数据库连接失败")
        self.destroy()

    def _restart_app(self) -> None:
        try:
            if self._scanner:
                self._scanner.stop()
        except Exception:
            pass
        self.destroy()
        try:
            import subprocess
            exe = sys.argv[0]
            subprocess.Popen([exe] + sys.argv[1:], creationflags=0x00000008)
        except Exception:
            logger.exception("重启程序失败")
        self.quit()


# ------------------------------------------------------------------ #
if __name__ == "__main__":
    app = CashierApp()
    try:
        from barcode_gun import BarcodeGun
        app._scanner = BarcodeGun(app._on_barcode_raw)
        app._scanner.start()
    except Exception:
        pass
    app.mainloop()
