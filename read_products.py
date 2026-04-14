#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import zipfile
import xml.etree.ElementTree as ET
import json

def read_xlsx_sheet(filepath, sheet_index=0):
    """Read a sheet from xlsx file using zipfile + XML approach"""
    ns = {
        'main': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
    }
    try:
        with zipfile.ZipFile(filepath, 'r') as z:
            shared_strings = []
            if 'xl/sharedStrings.xml' in z.namelist():
                with z.open('xl/sharedStrings.xml') as f:
                    tree = ET.parse(f)
                    root = tree.getroot()
                    for si in root.findall('main:si', ns):
                        text = ''
                        for t in si.findall('.//main:t', ns):
                            if t.text:
                                text += t.text
                        shared_strings.append(text)

            sheets = [n for n in z.namelist() if n.startswith('xl/worksheets/sheet') and n.endswith('.xml')]
            sheets.sort()
            if sheet_index >= len(sheets):
                return []

            with z.open(sheets[sheet_index]) as f:
                tree = ET.parse(f)
                root = tree.getroot()

            rows = []
            for row in root.findall('.//main:row', ns):
                row_data = []
                for cell in row.findall('main:c', ns):
                    t = cell.get('t', '')
                    v = cell.find('main:v', ns)
                    if v is not None and v.text is not None:
                        if t == 's':
                            try:
                                row_data.append(shared_strings[int(v.text)])
                            except:
                                row_data.append('')
                        else:
                            row_data.append(v.text)
                    else:
                        row_data.append('')
                rows.append(row_data)
            return rows
    except Exception as e:
        return [f"ERROR: {e}"]

# Focus on 拉萨环线 2026 products
base = '/Users/gakki/Library/Containers/com.tencent.WeWorkMac/Data/WeDrive'
lhasa_files = []

for root, dirs, files in os.walk(base):
    if '1.拉萨环线' in root and '2026年' in root and '停用' not in root:
        for f in files:
            if '行程' in f and f.endswith('.xlsx'):
                lhasa_files.append(os.path.join(root, f))

lhasa_files.sort()
print(f"=== 拉萨环线 行程文件 ({len(lhasa_files)}个) ===\n")
for fp in lhasa_files:
    fname = os.path.basename(fp)
    print(f"📄 {fname}")
    rows = read_xlsx_sheet(fp, 0)
    # Print first 20 rows to understand structure
    for i, row in enumerate(rows[:25]):
        if any(cell.strip() for cell in row):
            print(f"  Row{i}: {' | '.join(str(c)[:30] for c in row[:10])}")
    print()
