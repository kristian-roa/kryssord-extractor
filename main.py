import kryssord_no
import gratis_kryssord
import remarkable


def main():
    kryssord_path, solution_path = kryssord_no.download_crossword()
    # gratis_kryssord.download_gratiskryssord("https://www.gratiskryssord.no/kryssord/dagens/")
    remarkable.upload_to_remarkable(kryssord_path)
    remarkable.upload_to_remarkable(solution_path, True)


if __name__ == "__main__":
    main()
