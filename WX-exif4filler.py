#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
照片日期提取 + 填补并写回 EXIF
规则：
- 已有 EXIF 日期 → 原样保留
- 缺失日期 → 按 00:00:00 / 30:00:00 交替填补（同一天内）
"""
import os
import re
import tkinter as tk
from tkinter import filedialog, messagebox, Toplevel, Text, Scrollbar, END
from datetime import datetime, timedelta
from PIL import Image
from PIL.ExifTags import TAGS
import piexif
import pandas as pd


# ---------- 工具 ----------
def get_exif_datetime(image_path: str):
    try:
        img = Image.open(image_path)
        exif = img._getexif()
        if exif:
            for tag, value in exif.items():
                if TAGS.get(tag) == "DateTimeOriginal":
                    return datetime.strptime(value, "%Y:%m:%d %H:%M:%S")
    except Exception:
        pass
    return None


def set_exif_datetime(image_path: str, new_dt: datetime):
    try:
        img = Image.open(image_path)
        raw_exif = img.info.get("exif", b"")
        exif_dict = piexif.load(raw_exif) if raw_exif else {
            "0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}

        date_str = new_dt.strftime("%Y:%m:%d %H:%M:%S")
        exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal] = date_str.encode()
        exif_dict["Exif"][piexif.ExifIFD.DateTimeDigitized] = date_str.encode()
        exif_dict["0th"][piexif.ImageIFD.DateTime] = date_str.encode()

        for ifd in ("0th", "Exif"):
            if ifd in exif_dict:
                for k in [k for k, v in exif_dict[ifd].items() if v == b""]:
                    del exif_dict[ifd][k]

        exif_bytes = piexif.dump(exif_dict)
        img.save(image_path, exif=exif_bytes)
    except Exception as e:
        print(f"[ERROR] 写入 {image_path} 失败：{e}")


def extract_ym(fname):
    m = re.search(r"(\d{4}-\d{2})", fname)
    return m.group(1) if m else None


# ---------- 主流程 ----------
def main():
    root = tk.Tk()
    root.withdraw()

    folder = filedialog.askdirectory(title="请选择包含 JPG 照片的文件夹")
    if not folder:
        messagebox.showwarning("提示", "未选择文件夹，程序退出。")
        return

    files = sorted([f for f in os.listdir(folder) if f.lower().endswith(".jpg")])
    if not files:
        messagebox.showwarning("提示", "未找到 JPG 文件，程序退出。")
        return

    # 收集数据
    data = []
    for fname in files:
        full_path = os.path.join(folder, fname)
        dt = get_exif_datetime(full_path)
        data.append({"file": fname, "path": full_path,
                     "ym": extract_ym(fname), "date": dt})

    df = pd.DataFrame(data)

    # 按月分组填补
    def fill_month(group):
        group = group.sort_values("file").reset_index(drop=True)
        month_str = group.iloc[0]["ym"]
        if pd.isna(month_str):
            return group

        y, m = map(int, month_str.split("-"))
        base_day = datetime(y, m, 1)

        # 需要填补的索引
        na_idx = group[group["date"].isna()].index
        if na_idx.empty:
            return group

        # 用 30 分钟步进：00:00, 00:30, 01:00, 01:30 ...
        for seq, idx in enumerate(na_idx):
            total_min = seq * 30               # 每 30 分钟一个文件
            hour = (total_min // 60) % 24      # 保证 0-23
            minute = total_min % 60
            group.at[idx, "date"] = base_day.replace(
                hour=hour, minute=minute, second=0)

        return group

    filled = df.groupby("ym", group_keys=False).apply(fill_month)

    # 预览窗口
    preview = Toplevel()
    preview.title("日期提取+填补预览（确认后写入）")
    preview.geometry("600x400")

    txt = Text(preview, wrap="none")
    scroll_y = Scrollbar(preview, orient="vertical", command=txt.yview)
    txt.configure(yscrollcommand=scroll_y.set)
    scroll_y.pack(side="right", fill="y")
    txt.pack(fill="both", expand=True)

    for _, row in filled.iterrows():
        flag = "【补】" if row["date"].second == 0 and row["date"].minute in {0, 30} else "【原】"
        txt.insert(END,
                   f"{flag} {row['file']}  ->  {row['date'].strftime('%Y-%m-%d %H:%M:%S')}\n")

    def on_confirm():
        # 只把系统填补的写回
        for _, row in filled.iterrows():
            # 如果原来的 EXIF 为空才写回
            original = get_exif_datetime(row["path"])
            if original is None:
                set_exif_datetime(row["path"], row["date"])
        messagebox.showinfo("完成", "缺失日期已按 00/30 分钟填补并写回 EXIF！")
        preview.destroy()
        root.quit()

    def on_cancel():
        preview.destroy()
        root.quit()

    btn_frame = tk.Frame(preview)
    btn_frame.pack(pady=5)
    tk.Button(btn_frame, text="确认写入", command=on_confirm).pack(side="left", padx=10)
    tk.Button(btn_frame, text="取消", command=on_cancel).pack(side="left", padx=10)

    preview.focus()
    root.mainloop()


if __name__ == "__main__":
    main()