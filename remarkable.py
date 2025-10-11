#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import subprocess

REMARKABLE_FOLDER = "Kryssord"

def upload_to_remarkable(filename, is_solution=False):
    folder = REMARKABLE_FOLDER + "/Løsninger" if is_solution else REMARKABLE_FOLDER

    try:
        subprocess.run(["/opt/homebrew/bin/rmapi", "put", filename, folder], check=True)
        print(f"? Uploaded to reMarkable: {folder}/{filename}")
    except subprocess.CalledProcessError as e:
        print(f"? Failed to upload to reMarkable: {e}")
