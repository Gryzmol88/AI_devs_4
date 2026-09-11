import json

from csv_utils import load_people, prefilter
from llm_service import build_answer, send_answer, tag_jobs
from settings import Settings


if __name__ == "__main__":
    settings = Settings()

    people = load_people(settings.PEOPLE_CSV_URL)
    print(f"Wczytano rekordów: {len(people)}")

    filtered = prefilter(people, reference_year=settings.REFERENCE_YEAR)
    print(f"Po filtrze (M, Grudziądz, 20-40 lat w {settings.REFERENCE_YEAR}): {len(filtered)}")

    tags_map = tag_jobs(filtered, model=settings.OPENROUTER_MODEL)
    answer = build_answer(filtered, tags_map)

    print(f"Po tagu 'transport': {len(answer)}")
    print(json.dumps(answer, ensure_ascii=False, indent=2))

    settings.output_path.parent.mkdir(parents=True, exist_ok=True)
    settings.output_path.write_text(json.dumps(answer, ensure_ascii=False, indent=2), encoding="utf-8")

    result = send_answer(
        answer=answer,
        api_key=settings.hub_api_key,
        verify_url=settings.VERIFY_URL,
        task="people",
    )
    print("\nWynik z verify:")
    print(json.dumps(result, ensure_ascii=False, indent=2))



