import argparse
import kryssord_no
import gratis_kryssord
import remarkable


def download_and_upload_kryssord_no():
    kryssord_path, solution_path = kryssord_no.download_crossword()
    remarkable.upload_to_remarkable(kryssord_path)
    remarkable.upload_to_remarkable(solution_path, True)


def download_and_upload_gratis_kryssord():
    kryssord_path = gratis_kryssord.download_gratiskryssord("https://www.gratiskryssord.no/kryssord/dagens/")
    remarkable.upload_to_remarkable(kryssord_path)


def main():
    ap = argparse.ArgumentParser(description="Save crossword + solution as trimmed PDFs with date-based filenames.")
    ap.add_argument("--kryssord-no", default=False)
    ap.add_argument("--gratis-kryssord", default=True)
    args = ap.parse_args()

    if args.kryssord_no: download_and_upload_kryssord_no()
    if args.gratis_kryssord: download_and_upload_gratis_kryssord()


if __name__ == "__main__":
    main()
