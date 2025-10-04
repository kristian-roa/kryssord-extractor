import crossword_extractor
import remarkable


def main():
    kryssord_path, solution_path = crossword_extractor.download_crossword()
    remarkable.upload_to_remarkable(kryssord_path)
    remarkable.upload_to_remarkable(solution_path, True)


if __name__ == "__main__":
    main()
