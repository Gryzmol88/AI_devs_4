"""Program rozwiazujacy zadanie radiomonitoring."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import requests

from clients.central_api import CentralaApiClient
from clients.openrouter_client import OpenRouterClient
from config import get_settings
from models import FinalReport
from pipeline.attachment_processor import (
    decode_attachment_base64,
    extract_facts_from_nested_payload,
    parse_attachment_content,
)
from pipeline.audio_processor import AudioTranscriptionUnavailable, transcribe_audio_file
from pipeline.fact_aggregator import FactAggregator
from pipeline.llm_result_normalizer import normalize_llm_facts
from pipeline.router import classify_signal
from pipeline.transcription_processor import extract_facts_with_regex
from utils.io import create_run_output_dir, save_json, save_text
from utils.logger import log_error, log_info


def _extract_from_parsed_attachment(parsed_attachment: dict[str, Any]) -> dict[str, Any]:
    parsed = parsed_attachment.get("parsed")
    if isinstance(parsed, dict):
        return {
            "cityName": parsed.get("cityName") or parsed.get("city_name"),
            "cityArea": parsed.get("cityArea") or parsed.get("city_area"),
            "warehousesCount": parsed.get("warehousesCount") or parsed.get("warehouses_count"),
            "phoneNumber": parsed.get("phoneNumber") or parsed.get("phone_number"),
        }
    if isinstance(parsed, str):
        return extract_facts_with_regex(parsed)
    return {}


def _add_llm_candidates(aggregator: FactAggregator, llm_payload: dict[str, Any], source: str) -> None:
    normalized_items = normalize_llm_facts(llm_payload)
    if normalized_items:
        for item in normalized_items:
            aggregator.add_candidate_dict(item, source=source)
        return
    aggregator.add_candidate_dict(llm_payload, source=source)


def _guess_extension_from_mime(mime_type: str | None) -> str:
    normalized = (mime_type or "").lower().strip()
    mapping = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "image/bmp": ".bmp",
        "image/tiff": ".tiff",
        "audio/mpeg": ".mp3",
        "audio/mp3": ".mp3",
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
        "audio/ogg": ".ogg",
        "audio/webm": ".webm",
        "audio/flac": ".flac",
        "text/plain": ".txt",
        "text/csv": ".csv",
        "text/xml": ".xml",
        "application/json": ".json",
        "application/xml": ".xml",
    }
    return mapping.get(normalized, ".bin")


def _guess_extension_from_magic(raw_bytes: bytes) -> str | None:
    if raw_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if raw_bytes.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if raw_bytes.startswith(b"GIF87a") or raw_bytes.startswith(b"GIF89a"):
        return ".gif"
    if raw_bytes.startswith(b"RIFF") and raw_bytes[8:12] == b"WEBP":
        return ".webp"
    if raw_bytes.startswith((b"II*\x00", b"MM\x00*")):
        return ".tiff"
    if raw_bytes.startswith(b"BM"):
        return ".bmp"
    if raw_bytes.startswith(b"%PDF"):
        return ".pdf"
    return None


def _save_attachment_file(run_dir: Path, iteration: int, raw_bytes: bytes, meta: str | None) -> Path:
    extension = _guess_extension_from_magic(raw_bytes) or _guess_extension_from_mime(meta)
    path = run_dir / f"step2_attachment_raw_{iteration:03d}{extension}"
    path.write_bytes(raw_bytes)
    return path


def _safe_call(fn: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
    try:
        return fn(*args, **kwargs)
    except Exception as error:
        return {
            "cityName": None,
            "cityArea": None,
            "warehousesCount": None,
            "phoneNumber": None,
            "_error": str(error),
        }


def _build_warehouses_snippets(context_fragments: list[str]) -> list[str]:
    snippets: list[str] = []
    keywords = ["magazyn", "magazyny", "magazynow", "magazynĂłw", "sklad", "skĹ‚ad", "syjon"]
    for fragment in context_fragments:
        lowered = fragment.lower()
        if not any(keyword in lowered for keyword in keywords):
            continue
        if fragment not in snippets:
            snippets.append(fragment)
        for keyword in keywords:
            start = 0
            while True:
                idx = lowered.find(keyword, start)
                if idx == -1:
                    break
                left = max(0, idx - 500)
                right = min(len(fragment), idx + 500)
                snippet = fragment[left:right]
                if snippet not in snippets:
                    snippets.append(snippet)
                start = idx + len(keyword)
    return snippets


def _rescue_warehouses(
    aggregator: FactAggregator,
    openrouter_client: OpenRouterClient,
    context_fragments: list[str],
    selected_city: str | None,
    run_dir: Path,
) -> None:
    if aggregator.snapshot().get("warehousesCount"):
        return
    narrowed_fragments = context_fragments
    if selected_city:
        city_lower = selected_city.lower()
        city_hits = [fragment for fragment in context_fragments if city_lower in fragment.lower()]
        if city_hits:
            narrowed_fragments = city_hits
    snippets = _build_warehouses_snippets(narrowed_fragments)
    if not snippets:
        return
    save_json(run_dir / "step5_rescue_warehouses_snippets.json", {"snippets": snippets})
    merged = "\n\n---\n\n".join(snippets)
    payload = _safe_call(openrouter_client.extract_warehouses_count, merged)
    save_json(run_dir / "step5_rescue_warehouses_llm.json", payload)
    aggregator.add_candidate_dict(payload, source="rescue-warehouses-llm")
    if aggregator.snapshot().get("warehousesCount"):
        return
    # Druga prĂłba: tylko najbardziej relewantne fragmenty "aktualnego stanu".
    strict_candidates = [
        s
        for s in snippets
        if any(token in s.lower() for token in ["obecnie", "aktualnie", "stan", "mamy", "jest"])
    ]
    if strict_candidates:
        strict_payload = _safe_call(
            openrouter_client.extract_warehouses_count,
            "\n\n---\n\n".join(strict_candidates),
        )
        save_json(run_dir / "step5_rescue_warehouses_llm_strict.json", strict_payload)
        aggregator.add_candidate_dict(strict_payload, source="rescue-warehouses-llm")


def _is_future_context(text: str) -> bool:
    """Sprawdza, czy tekst opisuje stan planowany/przyszĹ‚y."""
    lowered = text.lower()
    markers = [
        "planujemy",
        "na wiosn",
        "wybudow",
        "zbudow",
        "powstanie",
        "docelowo",
        "bÄ™dzie",
        "bedzie",
        "zamierzamy",
    ]
    return any(marker in lowered for marker in markers)


def _sanitize_audio_llm_facts(llm_facts: dict[str, Any], transcription_text: str) -> dict[str, Any]:
    """CzyĹ›ci fakty z audio LLM tak, by nie przepuszczaÄ‡ planowanych wartoĹ›ci magazynĂłw."""
    sanitized = dict(llm_facts)
    if _is_future_context(transcription_text):
        sanitized["warehousesCount"] = None
    return sanitized


def _collect_city_area_from_payload(payload: Any) -> dict[str, str]:
    """Buduje mapÄ™ city->area z zaĹ‚Ä…cznikĂłw JSON/list."""
    result: dict[str, str] = {}
    if isinstance(payload, list):
        for item in payload:
            if not isinstance(item, dict):
                continue
            city = item.get("name") or item.get("cityName") or item.get("city_name")
            area = item.get("occupiedArea") or item.get("cityArea") or item.get("city_area")
            if city is None or area is None:
                continue
            city_text = str(city).strip()
            area_text = str(area).strip().replace(",", ".")
            if city_text and area_text:
                result[city_text] = area_text
    elif isinstance(payload, dict):
        city = payload.get("name") or payload.get("cityName") or payload.get("city_name")
        area = payload.get("occupiedArea") or payload.get("cityArea") or payload.get("city_area")
        if city is not None and area is not None:
            city_text = str(city).strip()
            area_text = str(area).strip().replace(",", ".")
            if city_text and area_text:
                result[city_text] = area_text
    return result


def _pick_city_from_area_map(
    city_candidates: list[str],
    city_area_map: dict[str, str],
) -> str | None:
    """Wybiera najczÄ™stsze miasto spoĹ›rĂłd kandydatĂłw, ale tylko z mapy area."""
    if not city_area_map:
        return None
    allowed = {key.lower(): key for key in city_area_map.keys()}
    counts: dict[str, int] = {}
    for item in city_candidates:
        lowered = item.lower()
        if lowered not in allowed:
            continue
        canonical = allowed[lowered]
        counts[canonical] = counts.get(canonical, 0) + 1
    if not counts:
        return None
    ranked = sorted(counts.items(), key=lambda x: (x[1], len(x[0])), reverse=True)
    return ranked[0][0]


def _sanitize_warehouses_for_city(
    final_payload: dict[str, Any],
    context_fragments: list[str],
) -> dict[str, Any]:
    """Usuwa warehousesCount, jeĹ›li nie ma wsparcia w kontekĹ›cie wybranego miasta."""
    city = str(final_payload.get("cityName", "")).strip()
    warehouses = final_payload.get("warehousesCount")
    if not city or warehouses is None:
        return final_payload
    city_lower = city.lower()
    has_city_link = any(
        city_lower in fragment.lower() and "magazyn" in fragment.lower()
        for fragment in context_fragments
    )
    if not has_city_link:
        final_payload["_warehouses_city_link_warning"] = True
    return final_payload


def _normalize_final_payload(final_payload: dict[str, Any], city_area_map: dict[str, str]) -> dict[str, Any]:
    """Koryguje payload koĹ„cowy do spĂłjnego cityName/cityArea."""
    city = str(final_payload.get("cityName", "")).strip()
    if not city:
        return final_payload
    if city in city_area_map:
        final_payload["cityArea"] = FinalReport.format_city_area(city_area_map[city])
        return final_payload
    # Brak area dla wybranego miasta: lepiej zwrĂłciÄ‡ bĹ‚Ä…d walidacji niĹĽ wysĹ‚aÄ‡ niespĂłjne dane.
    final_payload["cityArea"] = None
    return final_payload


def run() -> None:
    settings = get_settings()
    output_root = Path(settings.output_base_dir) / settings.output_task_subdir
    run_dir = create_run_output_dir(str(output_root), settings.timestamp_format)
    save_text(run_dir / "run_info.txt", f"Run directory: {run_dir}\n")
    log_info(f"Start programu. Katalog runa: {run_dir}")
    log_info(
        f"Modele OpenRouter: text={settings.openrouter_model}, vision={settings.openrouter_vision_model}"
    )

    centrala_client = CentralaApiClient(settings=settings)
    openrouter_client = OpenRouterClient(settings=settings)
    aggregator = FactAggregator()
    city_area_map: dict[str, str] = {}

    log_info("Inicjalizacja sesji nasluchu (action=start).")
    start_response = centrala_client.start_session()
    save_json(run_dir / "step0_start_response.json", start_response)

    collected: list[tuple[int, str, Any]] = []
    for iteration in range(1, settings.max_listen_iterations + 1):
        log_info(f"Nasluch iteracja {iteration} (action=listen).")
        signal = centrala_client.listen()
        save_json(run_dir / f"step1_listen_{iteration:03d}.json", signal.model_dump())
        signal_type = classify_signal(signal)
        log_info(f"Klasyfikacja sygnalu: {signal_type}")
        if signal_type == "end":
            log_info("Odebrano sygnal zakonczenia nasluchu.")
            break
        if signal_type in {"noise", "unknown"}:
            continue
        collected.append((iteration, signal_type, signal))
    else:
        log_error("Przekroczono limit iteracji nasluchu bez sygnalu konca.")

    log_info(f"Przetwarzanie batch: {len(collected)} elementow.")
    rescue_fragments: list[str] = []

    for iteration, signal_type, signal in collected:
        if signal_type == "transcription" and signal.transcription:
            rescue_fragments.append(signal.transcription)
            regex_facts = extract_facts_with_regex(signal.transcription)
            aggregator.add_candidate_dict(regex_facts, source="transcription-regex")
            save_json(run_dir / f"step2_transcription_regex_{iteration:03d}.json", regex_facts)
            if settings.use_llm_for_transcriptions:
                llm_facts = _safe_call(openrouter_client.extract_facts, signal.transcription)
                if llm_facts.get("_error"):
                    save_json(run_dir / f"step3_transcription_llm_error_{iteration:03d}.json", llm_facts)
                else:
                    _add_llm_candidates(aggregator, llm_facts, source="transcription-llm")
                    save_json(run_dir / f"step3_transcription_llm_{iteration:03d}.json", llm_facts)

        if signal_type == "attachment" and signal.attachment:
            raw_bytes = decode_attachment_base64(signal.attachment)
            raw_path = _save_attachment_file(run_dir, iteration, raw_bytes, signal.meta)
            log_info(f"Zapisano zalacznik: {raw_path.name}")
            parsed_attachment = parse_attachment_content(raw_bytes, signal.meta)
            save_json(run_dir / f"step2_attachment_parsed_{iteration:03d}.json", parsed_attachment)

            parsed = parsed_attachment.get("parsed")
            if isinstance(parsed, str) and parsed.strip():
                rescue_fragments.append(parsed)
            if isinstance(parsed, (dict, list)):
                rescue_fragments.append(str(parsed))
                city_area_map.update(_collect_city_area_from_payload(parsed))

            local_facts = _extract_from_parsed_attachment(parsed_attachment)
            nested_facts = extract_facts_from_nested_payload(parsed_attachment.get("parsed"))
            aggregator.add_candidate_dict(local_facts, source="attachment-local")
            aggregator.add_candidate_dict(nested_facts, source="attachment-nested")
            save_json(run_dir / f"step2_attachment_extracted_{iteration:03d}.json", nested_facts)

            should_use_llm = parsed_attachment.get("content_type") in {"text", "json", "json-invalid"}
            if should_use_llm and parsed_attachment.get("text_preview"):
                llm_facts = _safe_call(openrouter_client.extract_facts, str(parsed_attachment.get("text_preview")))
                if llm_facts.get("_error"):
                    save_json(run_dir / f"step3_attachment_llm_error_{iteration:03d}.json", llm_facts)
                else:
                    _add_llm_candidates(aggregator, llm_facts, source="attachment-llm")
                    save_json(run_dir / f"step3_attachment_llm_{iteration:03d}.json", llm_facts)

            if parsed_attachment.get("content_type") == "image" and signal.meta:
                vision_text_payload = _safe_call(
                    openrouter_client.extract_text_from_image_base64,
                    image_base64=signal.attachment,
                    mime_type=signal.meta,
                )
                vision_text = str(vision_text_payload.get("text") or "").strip()
                save_json(
                    run_dir / f"step2_attachment_vision_text_{iteration:03d}.json",
                    vision_text_payload,
                )
                if vision_text:
                    save_text(run_dir / f"step2_attachment_vision_text_{iteration:03d}.txt", vision_text)
                    rescue_fragments.append(vision_text)
                    vision_text_regex_facts = extract_facts_with_regex(vision_text)
                    aggregator.add_candidate_dict(vision_text_regex_facts, source="attachment-vision-llm")
                    save_json(
                        run_dir / f"step2_attachment_vision_text_extracted_{iteration:03d}.json",
                        vision_text_regex_facts,
                    )
                image_facts = _safe_call(
                    openrouter_client.extract_facts_from_image_base64,
                    image_base64=signal.attachment,
                    mime_type=signal.meta,
                )
                if not image_facts.get("_error"):
                    _add_llm_candidates(aggregator, image_facts, source="attachment-vision-llm")
                    save_json(run_dir / f"step3_attachment_vision_llm_{iteration:03d}.json", image_facts)
                vote = _safe_call(
                    openrouter_client.extract_warehouses_count_from_image_base64,
                    image_base64=signal.attachment,
                    mime_type=signal.meta,
                    samples=3,
                )
                save_json(run_dir / f"step3_attachment_vision_warehouses_vote_{iteration:03d}.json", vote)
                aggregator.add_candidate_dict(
                    {"warehousesCount": vote.get("warehousesCount")},
                    source="attachment-vision-warehouses-llm",
                )

            if (
                parsed_attachment.get("content_type") == "audio"
                and settings.enable_audio_transcription
            ):
                try:
                    audio_transcription = transcribe_audio_file(
                        audio_path=raw_path,
                        model_size=settings.whisper_model_size,
                        compute_type=settings.whisper_compute_type,
                    )
                    if audio_transcription:
                        save_text(
                            run_dir / f"step2_audio_transcription_{iteration:03d}.txt",
                            audio_transcription,
                        )
                        rescue_fragments.append(audio_transcription)
                        audio_regex_facts = extract_facts_with_regex(audio_transcription)
                        aggregator.add_candidate_dict(
                            audio_regex_facts, source="audio-transcription-regex"
                        )
                        save_json(
                            run_dir / f"step2_audio_transcription_regex_{iteration:03d}.json",
                            audio_regex_facts,
                        )
                        if settings.use_llm_for_transcriptions:
                            audio_llm_facts = _safe_call(
                                openrouter_client.extract_facts, audio_transcription
                            )
                            if audio_llm_facts.get("_error"):
                                save_json(
                                    run_dir / f"step3_audio_transcription_llm_error_{iteration:03d}.json",
                                    audio_llm_facts,
                                )
                            else:
                                sanitized_audio_llm_facts = _sanitize_audio_llm_facts(
                                    audio_llm_facts, audio_transcription
                                )
                                _add_llm_candidates(
                                    aggregator,
                                    sanitized_audio_llm_facts,
                                    source="audio-transcription-llm",
                                )
                                save_json(
                                    run_dir / f"step3_audio_transcription_llm_{iteration:03d}.json",
                                    sanitized_audio_llm_facts,
                                )
                except AudioTranscriptionUnavailable as error:
                    save_json(
                        run_dir / f"step2_audio_transcription_unavailable_{iteration:03d}.json",
                        {"error": str(error)},
                    )
                    log_error(
                        f"Brak backendu transkrypcji audio dla {raw_path.name}: {error}"
                    )

        save_json(run_dir / f"step4_aggregator_snapshot_{iteration:03d}.json", aggregator.snapshot())

    snapshot_before_rescue = aggregator.snapshot()
    city_candidates = snapshot_before_rescue.get("cityName", [])
    selected_city = _pick_city_from_area_map(city_candidates, city_area_map)
    _rescue_warehouses(aggregator, openrouter_client, rescue_fragments, selected_city, run_dir)

    try:
        final_report = aggregator.build_final_report()
    except Exception as error:
        error_payload = {
            "error": str(error),
            "snapshot": aggregator.snapshot(),
        }
        save_json(run_dir / "step5_final_report_error.json", error_payload)
        log_error(f"Nie udalo sie zbudowac finalnego raportu: {error}")
        return

    final_payload = final_report.model_dump()
    if selected_city:
        final_payload["cityName"] = selected_city
    final_payload = _normalize_final_payload(final_payload, city_area_map)
    final_payload = _sanitize_warehouses_for_city(final_payload, rescue_fragments)
    if final_payload.pop("_warehouses_city_link_warning", False):
        save_json(
            run_dir / "step5_final_report_warning.json",
            {
                "warning": "warehousesCount nie ma jednoznacznego wsparcia city+magazyn w kontekście.",
                "cityName": final_payload.get("cityName"),
                "payload": final_payload,
            },
        )
        log_info(
            "Ostrzezenie: warehousesCount bez jednoznacznego wsparcia city+magazyn. Kontynuuje transmit."
        )
    if final_payload.get("cityArea") is None:
        error_payload = {
            "error": "Niespojny payload: brak cityArea dla wybranego cityName.",
            "cityName": final_payload.get("cityName"),
            "city_area_map_keys": sorted(city_area_map.keys()),
            "snapshot": aggregator.snapshot(),
        }
        save_json(run_dir / "step5_final_report_error.json", error_payload)
        log_error("Wstrzymano transmit: brak spĂłjnego cityArea dla wybranego miasta.")
        return
    save_json(run_dir / "step5_final_report_payload.json", final_payload)
    log_info(f"Zbudowano raport: {final_payload}")

    try:
        transmit_response = centrala_client.transmit(final_payload)
        save_json(run_dir / "step6_transmit_response.json", transmit_response)
        log_info("Wyslano raport koncowy (action=transmit).")
    except requests.HTTPError as error:
        response_text = ""
        status_code = None
        if error.response is not None:
            status_code = error.response.status_code
            response_text = error.response.text
        save_json(
            run_dir / "step6_transmit_error.json",
            {
                "error": str(error),
                "status_code": status_code,
                "response_text": response_text,
                "payload": final_payload,
            },
        )
        log_error(
            f"Transmit odrzucony przez centralÄ™ (HTTP {status_code}). SzczegĂłĹ‚y zapisano w step6_transmit_error.json."
        )
        return


if __name__ == "__main__":
    try:
        run()
    except Exception as error:
        log_error(f"Blad krytyczny: {error}")


