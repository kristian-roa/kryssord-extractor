#!/home/root/python310/bin/python3
# -*- coding: utf-8 -*-

import io, json, time, uuid, requests
from datetime import date
from pathlib import Path
from PIL import Image

XOCHITL_FOLDER = "/home/root/.local/share/remarkable/xochitl/"
KRYSSORD_FOLDER_UUID = "bf25dbd6-13e2-4cae-a2f4-2978944a72a3"

def create_metadata(folder_uuid, filebase, visible_name):
    ts = str(int(time.time() * 1000))
    metadata = {
        "deleted": False,
        "lastModified": ts,
        "modified": False,
        "parent": folder_uuid,
        "type": "DocumentType",
        "version": 1,
        "visibleName": visible_name,
        "lastOpenedPage": 0,
        "createdTime": ts
    }

    with open(filebase + ".metadata", "w") as f:
        json.dump(metadata, f, indent=2)


def create_content(filebase):
    content = {
        "extraMetadata": {},
        "fileType": "pdf",
        "lastOpenedPage": 0,
        "lineHeight": -1,
        "margins": 100,
        "pageCount": 1,
        "textScale": 1,
        "transform": {},
        "orientation": "portrait"
    }
    with open(filebase + ".content", "w") as f:
        json.dump(content, f, indent=2)


def build_url(d):
    return f"https://www.gratiskryssord.no/content/images/{d:%Y/%m}/kryssord-{d:%d-%m-%y}.jpg"

def fetch_image():
    today = date.today()
    url = build_url(today)
    r = requests.get(url)

    if r.status_code == 200:
        img = Image.open(io.BytesIO(r.content)).convert("RGB")
        return img, today, url

    raise SystemExit("Could not find todays crossword image")

def download_gratiskryssord(local):
    img, used_date, url = fetch_image()
    doc_uuid = str(uuid.uuid4())
    visible_name = f"{used_date:%Y-%m-%d}-gratiskryssord"

    filebase = visible_name if local else str(Path(XOCHITL_FOLDER) / doc_uuid)

    if not local:
        create_metadata(KRYSSORD_FOLDER_UUID, filebase, visible_name)
        create_content(filebase)

    img.save(Path(filebase).with_suffix(".pdf"), "PDF", resolution=300.0)

    print(f"Saved '{visible_name}' from {url}")
