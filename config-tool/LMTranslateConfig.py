# -*- coding: utf-8 -*-
"""
LMTranslateConfig - graphical configurator for the PotPlayer LMTranslate plugin.

Manages "SubtitleTranslate - LMTranslate.yaml" next to this executable:
  - providers (add / edit / delete)
  - context window size
  - default model (provider-id/model-id) and API key
  - one-click API connectivity test

Build (Windows, Python 3.13 with tkinter):
  pyinstaller --onefile --windowed --uac-admin --name "SubtitleTranslate - LMTranslate" ^
      --icon "SubtitleTranslate - LMTranslate.ico" LMTranslateConfig.py

The --uac-admin manifest lets the tool save into Program Files.
"""
import json
import os
import sys
import urllib.request
import urllib.error

YAML_NAME = "SubtitleTranslate - LMTranslate.yaml"

HEADER = """# LMTranslate 配置（由 SubtitleTranslate - LMTranslate.exe 生成）
# provider-id 不能含斜线 /；地址填到 /v1 即可，插件自动补 /chat/completions
# context: 翻译上下文保留的最近字幕条数（0 = 关闭）
# default_model / api_key: PotPlayer 面板两个框留空时自动使用
# 注意：api_key 明文存储，勿将含密钥的本文件分享给他人
"""


# ---------------- yaml io (same dialect as the plugin) ----------------

def parse_yaml(text):
    cfg = {"context": 8, "default_model": "", "api_key": "", "providers": {}}
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, val = line.split(":", 1)
        key, val = key.strip(), val.strip()
        if not key or not val:
            continue
        lk = key.lower()
        if lk == "context":
            cfg["context"] = 0 if val.lower() == "off" else int("".join(c for c in val if c.isdigit()) or 0)
        elif lk == "default_model":
            cfg["default_model"] = val
        elif lk == "api_key":
            cfg["api_key"] = val
        elif "/" not in key and (val.startswith("http://") or val.startswith("https://")):
            cfg["providers"][key] = val
    return cfg


def dump_yaml(cfg):
    lines = [HEADER, "context: %d" % cfg["context"], ""]
    if cfg["default_model"]:
        lines.append("default_model: %s" % cfg["default_model"])
    if cfg["api_key"]:
        lines.append("api_key: %s" % cfg["api_key"])
    if cfg["default_model"] or cfg["api_key"]:
        lines.append("")
    lines.append("providers:")
    for pid, url in cfg["providers"].items():
        lines.append("  %s: %s" % (pid, url))
    return "\n".join(lines) + "\n"


def yaml_path():
    base = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))
    return os.path.join(base, YAML_NAME)


def endpoint_of(url):
    url = url.strip().rstrip("/")
    if "chat/completions" in url.lower():
        return url
    return url + "/chat/completions"


def test_api(url, model, key, timeout=20):
    body = {
        "model": model,
        "messages": [{"role": "user", "content": "Translate to Chinese, output only the translation: hello world"}],
        "temperature": 0,
        "stream": False,
    }
    req = urllib.request.Request(
        endpoint_of(url),
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 **({"Authorization": "Bearer " + key} if key else {})},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"].strip()


# ---------------- selftest (headless) ----------------

def selftest(path):
    src = path if os.path.exists(path) else yaml_path()
    with open(src, "r", encoding="utf-8") as f:
        cfg = parse_yaml(f.read())
    out = os.path.join(os.environ.get("TEMP", "."), "lmtranslate_selftest.yaml")
    with open(out, "w", encoding="utf-8") as f:
        f.write(dump_yaml(cfg))
    with open(out, "r", encoding="utf-8") as f:
        cfg2 = parse_yaml(f.read())
    assert cfg == cfg2, "round-trip mismatch"
    print("SELFTEST OK providers=%d context=%d" % (len(cfg["providers"]), cfg["context"]))


# ---------------- GUI ----------------

def run_gui():
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog

    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    path = yaml_path()
    if not os.path.exists(path):
        picked = filedialog.askopenfilename(
            title="未找到配置文件，请手动选择 %s" % YAML_NAME,
            filetypes=[("LMTranslate YAML", "*.yaml"), ("所有文件", "*.*")])
        if not picked:
            return
        path = picked

    with open(path, "r", encoding="utf-8") as f:
        cfg = parse_yaml(f.read())

    root = tk.Tk()
    root.title("LMTranslate 图形配置")
    root.geometry("760x560")
    root.minsize(640, 480)

    style = ttk.Style(root)
    if "vista" in style.theme_names():
        style.theme_use("vista")

    main = ttk.Frame(root, padding=12)
    main.pack(fill="both", expand=True)

    # ---- default model / key ----
    cred = ttk.LabelFrame(main, text="默认模型与密钥（PotPlayer 面板留空时自动使用）", padding=10)
    cred.pack(fill="x")
    cred.columnconfigure(1, weight=1)

    ttk.Label(cred, text="模型 (provider/model)：").grid(row=0, column=0, sticky="w", pady=3)
    model_var = tk.StringVar(value=cfg["default_model"])
    ttk.Entry(cred, textvariable=model_var).grid(row=0, column=1, columnspan=2, sticky="ew", pady=3)

    ttk.Label(cred, text="API 密钥：").grid(row=1, column=0, sticky="w", pady=3)
    key_var = tk.StringVar(value=cfg["api_key"])
    key_entry = ttk.Entry(cred, textvariable=key_var, show="*")
    key_entry.grid(row=1, column=1, sticky="ew", pady=3)
    show_var = tk.BooleanVar(value=False)

    def toggle_show():
        key_entry.config(show="" if show_var.get() else "*")

    ttk.Checkbutton(cred, text="显示", variable=show_var, command=toggle_show).grid(row=1, column=2, padx=(6, 0))

    # ---- context ----
    ctxframe = ttk.Frame(main)
    ctxframe.pack(fill="x", pady=(10, 4))
    ttk.Label(ctxframe, text="翻译上下文条数（0 = 关闭）：").pack(side="left")
    ctx_var = tk.IntVar(value=cfg["context"])
    ttk.Spinbox(ctxframe, from_=0, to=50, textvariable=ctx_var, width=6).pack(side="left", padx=6)
    ttk.Label(ctxframe, text="最近 N 条原文→译文作为对话历史，保持人名/代词/术语一致",
              foreground="#666").pack(side="left", padx=8)

    # ---- providers ----
    pf = ttk.LabelFrame(main, text="服务商（providers）", padding=10)
    pf.pack(fill="both", expand=True, pady=(6, 4))

    cols = ("id", "url")
    tree = ttk.Treeview(pf, columns=cols, show="headings", height=10)
    tree.heading("id", text="provider-id")
    tree.heading("url", text="API 地址")
    tree.column("id", width=150, stretch=False)
    tree.column("url", width=420)
    sb = ttk.Scrollbar(pf, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=sb.set)
    tree.pack(side="left", fill="both", expand=True)
    sb.pack(side="left", fill="y")

    def refresh_tree():
        tree.delete(*tree.get_children())
        for pid, url in cfg["providers"].items():
            tree.insert("", "end", values=(pid, url))

    def edit_dialog(pid="", url=""):
        dlg = tk.Toplevel(root)
        dlg.title("编辑服务商" if pid else "新增服务商")
        dlg.geometry("480x150")
        dlg.transient(root)
        dlg.grab_set()
        frm = ttk.Frame(dlg, padding=12)
        frm.pack(fill="both", expand=True)
        frm.columnconfigure(1, weight=1)
        ttk.Label(frm, text="provider-id：").grid(row=0, column=0, sticky="w", pady=4)
        id_var = tk.StringVar(value=pid)
        id_entry = ttk.Entry(frm, textvariable=id_var)
        id_entry.grid(row=0, column=1, sticky="ew", pady=4)
        if pid:
            id_entry.state(["disabled"])
        ttk.Label(frm, text="API 地址：").grid(row=1, column=0, sticky="w", pady=4)
        url_var = tk.StringVar(value=url)
        ttk.Entry(frm, textvariable=url_var).grid(row=1, column=1, sticky="ew", pady=4)

        def ok():
            p, u = id_var.get().strip(), url_var.get().strip()
            if not p or "/" in p or ":" in p:
                messagebox.showerror("错误", "provider-id 不能为空，且不能含 / 或 :", parent=dlg)
                return
            if not (u.startswith("http://") or u.startswith("https://")):
                messagebox.showerror("错误", "地址必须以 http:// 或 https:// 开头", parent=dlg)
                return
            if not pid and p in cfg["providers"]:
                messagebox.showerror("错误", "provider-id 已存在", parent=dlg)
                return
            cfg["providers"][p] = u
            refresh_tree()
            dlg.destroy()

        bf = ttk.Frame(frm)
        bf.grid(row=2, column=0, columnspan=2, pady=(10, 0))
        ttk.Button(bf, text="确定", command=ok).pack(side="left", padx=4)
        ttk.Button(bf, text="取消", command=dlg.destroy).pack(side="left", padx=4)
        id_entry.focus_set()

    def add():
        edit_dialog()

    def edit():
        sel = tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先选中一行")
            return
        pid, url = tree.item(sel[0], "values")
        edit_dialog(pid, url)

    def delete():
        sel = tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先选中一行")
            return
        pid = tree.item(sel[0], "values")[0]
        if messagebox.askyesno("确认", "删除服务商 %s ？" % pid):
            cfg["providers"].pop(pid, None)
            refresh_tree()

    bf = ttk.Frame(main)
    bf.pack(fill="x", pady=(0, 6))
    ttk.Button(bf, text="新增", command=add).pack(side="left", padx=(0, 6))
    ttk.Button(bf, text="编辑", command=edit).pack(side="left", padx=6)
    ttk.Button(bf, text="删除", command=delete).pack(side="left", padx=6)
    ttk.Label(bf, text="配置文件：%s" % path, foreground="#666").pack(side="right")

    # ---- bottom actions ----
    act = ttk.Frame(main)
    act.pack(fill="x", pady=(4, 0))
    status_var = tk.StringVar(value="就绪")
    ttk.Label(act, textvariable=status_var, foreground="#0a7").pack(side="right")

    def collect():
        cfg["context"] = max(0, int(ctx_var.get()))
        cfg["default_model"] = model_var.get().strip()
        cfg["api_key"] = key_var.get().strip()

    def save():
        collect()
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(dump_yaml(cfg))
            status_var.set("已保存 ✓")
        except PermissionError:
            messagebox.showerror("保存失败", "没有写入权限：请右键本程序「以管理员身份运行」，\n或把程序放到插件目录外再手动复制 yaml。")
        except Exception as e:
            messagebox.showerror("保存失败", str(e))

    def do_test():
        collect()
        spec = cfg["default_model"]
        if "/" not in spec:
            messagebox.showinfo("提示", "请先填写默认模型，格式 provider-id/model-id")
            return
        pid, model = spec.split("/", 1)
        url = cfg["providers"].get(pid)
        if not url:
            messagebox.showerror("错误", "未找到服务商 %s，请先在列表中配置" % pid)
            return
        status_var.set("测试中…")
        root.update_idletasks()

        def work():
            try:
                ret = test_api(url, model, cfg["api_key"])
                root.after(0, lambda: (status_var.set("测试成功 ✓"),
                                       messagebox.showinfo("API 测试成功", "模型响应：\n%s" % ret)))
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", "replace")[:400]
                root.after(0, lambda: (status_var.set("测试失败"),
                                       messagebox.showerror("API 测试失败", "HTTP %d\n%s" % (e.code, detail))))
            except Exception as e:
                root.after(0, lambda: (status_var.set("测试失败"),
                                       messagebox.showerror("API 测试失败", str(e))))

        import threading
        threading.Thread(target=work, daemon=True).start()

    ttk.Button(act, text="保存配置", command=save).pack(side="left", padx=(0, 8))
    ttk.Button(act, text="测试 API 连通", command=do_test).pack(side="left")

    refresh_tree()
    root.mainloop()


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        i = sys.argv.index("--selftest")
        selftest(sys.argv[i + 1] if len(sys.argv) > i + 1 else "")
    else:
        run_gui()