#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
归档迁移 · 本地解析 -> 生成 PostgreSQL 插入 SQL
读取 D:\Workduddy\_ARCHIVE_2026-10-27 下的 6 个任务 XML + zip，
解析为结构化数据，产出插入 SQL（package 1 行 + tasks 6 行）。
建表(DDL)走 applyMigration，本脚本只产出 DML 插入语句。
"""
import os
import json
import xml.etree.ElementTree as ET
from datetime import datetime

ARCHIVE_DIR = r"D:\Workduddy\_ARCHIVE_2026-10-27"
SCHTASKS_DIR = os.path.join(ARCHIVE_DIR, "schtasks")
ZIP_PATH = os.path.join(ARCHIVE_DIR, "workbuddy-old-20261012.zip")
PACKAGE_NAME = "buddy-keeper-archive-2026-10-27"
SOURCE_MACHINE = "PC-20260923QRMI"
OPERATOR = "徐"
NOTE = "2026-10-27 本地注销 6 条 Windows 自动签到/旅行计划任务后的归档迁移"
ZIP_STORAGE_KEY = "archives/buddy-keeper-2026-10-27/workbuddy-old-20261012.zip"

NS = "{http://schemas.microsoft.com/windows/2004/02/mit/task}"


def local(tag):
    return tag if not tag.startswith(NS) else tag[len(NS):]


def xml_to_dict(el):
    d = {}
    if el.attrib:
        d["@attributes"] = dict(el.attrib)
    children = list(el)
    if children:
        for c in children:
            cd = xml_to_dict(c)
            if local(c.tag) in d:
                if not isinstance(d[local(c.tag)], list):
                    d[local(c.tag)] = [d[local(c.tag)]]
                d[local(c.tag)].append(cd)
            else:
                d[local(c.tag)] = cd
        return d
    text = el.text
    if text is not None and text.strip() == "":
        text = None
    if el.attrib:
        d["#text"] = text
        return d
    return text if text is not None else None


def q(s):
    if s is None:
        return "NULL"
    return "'" + str(s).replace("'", "''") + "'"


def q_json(obj):
    return "'" + json.dumps(obj, ensure_ascii=False).replace("'", "''") + "'::jsonb"


def read_xml_text(path):
    with open(path, "rb") as f:
        b = f.read()
    if b[:3] == b"\xef\xbb\xbf":
        return b.decode("utf-8-sig")
    if b[:2] == b"\xff\xfe":
        return b[2:].decode("utf-16-le")
    if b[:2] == b"\xfe\xff":
        return b[2:].decode("utf-16-be")
    try:
        return b.decode("utf-16-le")
    except UnicodeDecodeError:
        return b.decode("utf-8")


def parse_task(xml_path):
    raw_xml = read_xml_text(xml_path)
    root = ET.fromstring(raw_xml)

    uri = root.findtext(f".//{NS}RegistrationInfo/{NS}URI")
    task_name = (uri or "").lstrip("\\")
    description = root.findtext(f".//{NS}RegistrationInfo/{NS}Description")

    principal = root.find(f".//{NS}Principals/{NS}Principal")
    principal_user = principal.findtext(f"{NS}UserId") if principal is not None else None
    logon_type = principal.findtext(f"{NS}LogonType") if principal is not None else None

    enabled_el = root.find(f".//{NS}Settings/{NS}Enabled")
    enabled = True
    if enabled_el is not None and enabled_el.text is not None:
        enabled = enabled_el.text.strip().lower() != "false"

    settings_el = root.find(f".//{NS}Settings")
    settings_json = xml_to_dict(settings_el) if settings_el is not None else None

    triggers_el = root.find(f".//{NS}Triggers")
    trigger_type = None
    trigger_detail = None
    if triggers_el is not None and list(triggers_el):
        trig = list(triggers_el)[0]
        trigger_type = local(trig.tag)
        trigger_detail = xml_to_dict(trig)

    action = root.find(f".//{NS}Actions/{NS}Exec")
    action_command = action.findtext(f"{NS}Command") if action is not None else None
    action_args = action.findtext(f"{NS}Arguments") if action is not None else None
    working_directory = action.findtext(f"{NS}WorkingDirectory") if action is not None else None

    return {
        "task_name": task_name,
        "description": description,
        "trigger_type": trigger_type,
        "trigger_detail": trigger_detail,
        "principal_user": principal_user,
        "logon_type": logon_type,
        "action_command": action_command,
        "action_args": action_args,
        "working_directory": working_directory,
        "enabled": enabled,
        "settings_json": settings_json,
        "raw_xml": raw_xml,
    }


def main():
    xml_files = sorted(
        os.path.join(SCHTASKS_DIR, f)
        for f in os.listdir(SCHTASKS_DIR)
        if f.lower().endswith(".xml")
    )
    tasks = [parse_task(p) for p in xml_files]

    zip_size = os.path.getsize(ZIP_PATH) if os.path.exists(ZIP_PATH) else None

    lines = []
    lines.append("-- 归档迁移 DML（package + 6 tasks）")
    lines.append("-- 由 generate_archive_migration.py 生成，package_name 唯一，重跑同包幂等跳过")
    lines.append("")
    lines.append("INSERT INTO archived_task_packages "
                 "(package_name, source_machine, operator, zip_storage_key, zip_size_bytes, note)")
    lines.append("SELECT " + ", ".join([
        q(PACKAGE_NAME), q(SOURCE_MACHINE), q(OPERATOR),
        q(ZIP_STORAGE_KEY), "NULL" if zip_size is None else str(zip_size), q(NOTE)
    ]) + " ")
    lines.append("WHERE NOT EXISTS (SELECT 1 FROM archived_task_packages WHERE package_name = " + q(PACKAGE_NAME) + ");")
    lines.append("")

    task_rows = []
    pkg_sub = "(SELECT id FROM archived_task_packages WHERE package_name = " + q(PACKAGE_NAME) + ")"
    for t in tasks:
        vals = [
            pkg_sub, q(t["task_name"]), q(t["description"]), q(t["trigger_type"]),
            q_json(t["trigger_detail"]), q(t["principal_user"]), q(t["logon_type"]),
            q(t["action_command"]), q(t["action_args"]), q(t["working_directory"]),
            "true" if t["enabled"] else "false", q_json(t["settings_json"]), q(t["raw_xml"]),
        ]
        row = "SELECT " + ", ".join(vals)
        row += (" WHERE NOT EXISTS (SELECT 1 FROM archived_scheduled_tasks t "
                "WHERE t.package_id = " + pkg_sub + " AND t.task_name = " + q(t["task_name"]) + ")")
        task_rows.append(row)
    lines.append("INSERT INTO archived_scheduled_tasks "
                 "(package_id, task_name, description, trigger_type, trigger_detail, "
                 "principal_user, logon_type, action_command, action_args, "
                 "working_directory, enabled, settings_json, raw_xml)")
    lines.append("\nUNION ALL\n".join(task_rows) + ";")
    lines.append("")

    sql = "\n".join(lines)

    # 输出 1：本地留档
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "archive_insert.sql")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(sql)

    # 输出 2：cloudbase/migrations/<version>_<name>.sql（供 tcb db pg migration up 执行）
    version = os.environ.get("MIGRATION_VERSION", datetime.now().strftime("%Y%m%d%H%M%S"))
    mig_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "cloudbase", "migrations")
    os.makedirs(mig_dir, exist_ok=True)
    mig_path = os.path.join(mig_dir, f"{version}_insert_archive_data.sql")
    with open(mig_path, "w", encoding="utf-8") as f:
        f.write(sql)

    print("PARSED TASKS:", len(tasks))
    for t in tasks:
        print(f"  - {t['task_name']:24s} trig={t['trigger_type']:16s} enabled={t['enabled']}")
    print("ZIP SIZE BYTES:", zip_size)
    print("SQL WRITTEN TO:", out_path)
    print("MIGRATION FILE:", mig_path)
    print("MIGRATION VERSION:", version)
    print("SQL LENGTH:", len(sql))


if __name__ == "__main__":
    main()
