import subprocess

REMARKABLE_FOLDER = "Kryssord"

def upload_to_remarkable(filename, is_solution=False):
    folder = REMARKABLE_FOLDER + "/Løsninger" if is_solution else REMARKABLE_FOLDER

    try:
        subprocess.run(["/usr/local/bin/rmapi", "put", filename, REMARKABLE_FOLDER], check=True)
        print(f"? Uploaded to reMarkable: {REMARKABLE_FOLDER}/{filename}")
    except subprocess.CalledProcessError as e:
        print(f"? Failed to upload to reMarkable: {e}")
