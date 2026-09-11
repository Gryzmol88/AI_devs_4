"""Runner misji pobocznej: unlock + mirror eksperymenty."""

from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from clients.aidevs_api import AIDevsApiClient
from config import AppSettings
from utils.io import write_json
from utils.io import write_text
from utils.logger import log_info
from utils.logger import log_warn


class SideMissionRunner:
    """Wykonuje zestaw scenariuszy i zapisuje dokladny output z timestamp."""

    def __init__(self, settings: AppSettings, api_client: AIDevsApiClient, run_output_dir: str) -> None:
        self._settings = settings
        self._api_client = api_client
        self._run_output_dir = Path(run_output_dir)
        self._live_trace_path = self._path("live_trace.ndjson")

    def run(self) -> dict[str, Any]:
        started_at = time.time()
        cases = self._build_cases(max_cases=self._settings.app_max_cases)
        write_json(
            self._path("step1_loaded_cases.json"),
            {
                "loadedAt": self._iso_now(),
                "maxCases": self._settings.app_max_cases,
                "cases": cases,
            },
        )

        log_info(f"Zaladowano {len(cases)} case'ow (limit={self._settings.app_max_cases}).")
        results: list[dict[str, Any]] = []
        for index, case in enumerate(cases, start=1):
            log_info(f"Case {index}/{len(cases)}: {case['name']} ({case['family']})")
            case_result = self._run_case(case=case)
            results.append(case_result)
            if case_result.get("flag"):
                log_info("Wykryto flage - koncze dalsze testy.")
                break

        write_json(
            self._path("step2_unlock_then_mirror_config_results.json"),
            {
                "generatedAt": self._iso_now(),
                "results": results,
            },
        )

        summary = self._build_summary(results=results, elapsed_seconds=time.time() - started_at)
        write_json(self._path("step3_unlock_then_mirror_config_summary.json"), summary)
        write_text(self._path("final_result.txt"), str(summary))
        return summary

    def _run_case(self, case: dict[str, Any]) -> dict[str, Any]:
        traces: list[dict[str, Any]] = []

        start_resp = self._invoke({"action": "start"}, traces, case_name=case["name"], label="start")
        unlock_resp = self._invoke(
            {"action": "unlockCodeGenerator", **case["unlock"]},
            traces,
            case_name=case["name"],
            label="unlockCodeGenerator",
        )

        unlock_result = self._poll_for_source(
            source_function="unlockCodeGenerator",
            traces=traces,
            case_name=case["name"],
        )
        unlock_code = self._extract_unlock_code(unlock_result)
        found_flag = self._find_flag([start_resp, unlock_resp, unlock_result])
        if found_flag:
            log_info(f"[{case['name']}] Wykryto flage w odpowiedzi unlock.")
            return {
                "case": case,
                "executedAt": self._iso_now(),
                "unlockCode": unlock_code,
                "flag": found_flag,
                "responses": {
                    "start": start_resp,
                    "unlockEnqueue": unlock_resp,
                    "unlockResult": unlock_result,
                    "config": {"skipped": True, "reason": "flag found in unlock response"},
                    "postConfigResult": {"skipped": True, "reason": "flag found in unlock response"},
                },
                "trace": traces,
            }
        if not unlock_code:
            log_warn(f"[{case['name']}] Brak unlockCode.")
            return {
                "case": case,
                "executedAt": self._iso_now(),
                "unlockCode": "",
                "flag": self._find_flag([start_resp, unlock_resp, unlock_result]),
                "responses": {
                    "start": start_resp,
                    "unlockEnqueue": unlock_resp,
                    "unlockResult": unlock_result,
                    "config": {"skipped": True, "reason": "missing unlockCode"},
                    "postConfigResult": {"skipped": True, "reason": "missing unlockCode"},
                },
                "trace": traces,
            }
        if not re.fullmatch(r"[a-fA-F0-9]{32}", unlock_code):
            log_warn(f"[{case['name']}] unlockCode nie jest md5, pomijam config.")
            return {
                "case": case,
                "executedAt": self._iso_now(),
                "unlockCode": unlock_code,
                "flag": "",
                "responses": {
                    "start": start_resp,
                    "unlockEnqueue": unlock_resp,
                    "unlockResult": unlock_result,
                    "config": {"skipped": True, "reason": "unlockCode is not md5"},
                    "postConfigResult": {"skipped": True, "reason": "unlockCode is not md5"},
                },
                "trace": traces,
            }
        log_info(f"[{case['name']}] unlockCode={unlock_code}")

        config_answer = {
            "action": "config",
            "startDate": case["config"]["startDate"],
            "startHour": case["config"]["startHour"],
            "pitchAngle": case["config"]["pitchAngle"],
            "turbineMode": case["config"]["turbineMode"],
            "unlockCode": unlock_code,
        }
        config_resp = self._invoke(config_answer, traces, case_name=case["name"], label="config")

        post_config_result = self._poll_for_any_message(traces=traces, case_name=case["name"])

        found_flag = self._find_flag([start_resp, unlock_resp, unlock_result, config_resp, post_config_result])

        return {
            "case": case,
            "executedAt": self._iso_now(),
            "unlockCode": unlock_code,
            "flag": found_flag,
            "responses": {
                "start": start_resp,
                "unlockEnqueue": unlock_resp,
                "unlockResult": unlock_result,
                "config": config_resp,
                "postConfigResult": post_config_result,
            },
            "trace": traces,
        }

    def _invoke(
        self,
        answer: dict[str, Any],
        traces: list[dict[str, Any]],
        case_name: str,
        label: str,
    ) -> dict[str, Any]:
        response, trace = self._api_client.call(answer)
        trace["case"] = case_name
        trace["label"] = label
        traces.append(trace)
        self._append_live_trace(trace)

        code = response.get("code")
        source = response.get("sourceFunction")
        message = response.get("message", "")
        msg_preview = str(message)[:110]
        log_info(f"[{case_name}] {label} -> code={code} source={source} msg={msg_preview}")
        return response

    def _poll_for_source(self, source_function: str, traces: list[dict[str, Any]], case_name: str) -> dict[str, Any]:
        deadline = time.time() + self._settings.app_poll_timeout_seconds
        attempt = 0
        while time.time() < deadline:
            attempt += 1
            response = self._invoke(
                {"action": "getResult"},
                traces,
                case_name=case_name,
                label=f"getResult-unlock-poll#{attempt}",
            )
            source = response.get("sourceFunction")
            nested = response.get("result")
            if not source and isinstance(nested, dict):
                source = nested.get("sourceFunction")
            if source == source_function:
                log_info(f"[{case_name}] unlock wynik odebrany po {attempt} pollach.")
                return response
            if response.get("code") == 11 and attempt % 5 == 0:
                log_info(f"[{case_name}] unlock poll ongoing ({attempt} prob).")
            time.sleep(self._settings.app_poll_interval_seconds)
        return {"timeout": True, "expectedSource": source_function}

    def _poll_for_any_message(self, traces: list[dict[str, Any]], case_name: str) -> dict[str, Any]:
        max_idle_polls = 8
        deadline = time.time() + min(self._settings.app_poll_timeout_seconds, 4)
        attempt = 0
        while time.time() < deadline:
            attempt += 1
            response = self._invoke(
                {"action": "getResult"},
                traces,
                case_name=case_name,
                label=f"getResult-post-config-poll#{attempt}",
            )
            code = response.get("code")
            if code != 11:
                return response
            if attempt >= max_idle_polls:
                return {"message": "No queued message after config in fast-poll window.", "code": 11}
            if attempt % 5 == 0:
                log_info(f"[{case_name}] post-config poll ongoing ({attempt} prob).")
            time.sleep(self._settings.app_poll_interval_seconds)
        return {"timeout": True, "message": "No non-empty queued message after config."}

    @staticmethod
    def _extract_unlock_code(response: dict[str, Any]) -> str:
        for key in ("unlockCode", "signature", "hash"):
            value = response.get(key)
            if isinstance(value, str) and len(value) >= 8:
                return value
        direct_result = response.get("result")
        if isinstance(direct_result, str) and len(direct_result) >= 8:
            return direct_result
        nested = response.get("result")
        if isinstance(nested, dict):
            return SideMissionRunner._extract_unlock_code(nested)
        data = response.get("data")
        if isinstance(data, dict):
            return SideMissionRunner._extract_unlock_code(data)
        return ""

    @staticmethod
    def _find_flag(responses: list[dict[str, Any]]) -> str:
        needles = ("{FLG:", "FLAG{", "secret", "sekret")
        for response in responses:
            flat = str(response)
            if any(needle in flat for needle in needles):
                if "{FLG:" in flat:
                    start = flat.find("{FLG:")
                    end = flat.find("}", start)
                    if start >= 0 and end > start:
                        return flat[start : end + 1]
                return flat
        return ""

    def _build_summary(self, results: list[dict[str, Any]], elapsed_seconds: float) -> dict[str, Any]:
        found = [item for item in results if item.get("flag")]
        return {
            "generatedAt": self._iso_now(),
            "totalCasesExecuted": len(results),
            "flagFound": bool(found),
            "flag": found[0]["flag"] if found else "",
            "matchedCases": [item["case"]["name"] for item in found],
            "elapsedSeconds": round(elapsed_seconds, 3),
            "outputDir": str(self._run_output_dir),
        }

    @staticmethod
    def _build_cases(max_cases: int) -> list[dict[str, Any]]:
        now = datetime.now()
        normal_date = now.strftime("%Y-%m-%d")
        normal_hour = now.strftime("%H:00:00")

        palindrome_dates = ["2020-02-02", "2001-10-02", "2112-11-12"]
        mirror_hours = [
            "00:00:00",
            "01:10:00",
            "02:20:00",
            "10:01:00",
            "11:11:00",
            "12:21:00",
            "13:31:00",
            "23:32:00",
        ]
        mirror_winds: list[float | int] = [4.4, 5.5, 11, 12, 21, 22, 23, 32, 33]
        normal_winds: list[float | int] = [6, 8, 10, 12]
        pitch_angles = [0, 45, 90]

        def default_mode(pitch: int) -> str:
            return "idle" if pitch == 90 else "production"

        all_cases: list[dict[str, Any]] = []

        # Priorytet 1: pelne lustro dla unlock i config (najblizej hintom forum).
        for d in palindrome_dates:
            for h in mirror_hours:
                for w in mirror_winds:
                    for p in pitch_angles:
                        all_cases.append(
                            {
                                "name": f"P1_sameMirror_{d}_{h}_w{w}_p{p}",
                                "family": "P1_same_mirror",
                                "unlock": {
                                    "startDate": d,
                                    "startHour": h,
                                    "windMs": w,
                                    "pitchAngle": p,
                                },
                                "config": {
                                    "startDate": d,
                                    "startHour": h,
                                    "pitchAngle": p,
                                    "turbineMode": default_mode(p),
                                },
                            }
                        )

        # Priorytet 2: unlock lustrzany, config normalny.
        for d in palindrome_dates:
            for h in mirror_hours:
                for w in mirror_winds:
                    for p in pitch_angles:
                        all_cases.append(
                            {
                                "name": f"P2_unlockMirror_configNormal_{d}_{h}_w{w}_p{p}",
                                "family": "P2_unlock_mirror",
                                "unlock": {
                                    "startDate": d,
                                    "startHour": h,
                                    "windMs": w,
                                    "pitchAngle": p,
                                },
                                "config": {
                                    "startDate": normal_date,
                                    "startHour": normal_hour,
                                    "pitchAngle": p,
                                    "turbineMode": default_mode(p),
                                },
                            }
                        )

        # Priorytet 3: unlock normalny, config lustrzany.
        for d in palindrome_dates:
            for h in mirror_hours:
                for w in normal_winds:
                    for p in pitch_angles:
                        all_cases.append(
                            {
                                "name": f"P3_unlockNormal_configMirror_{d}_{h}_w{w}_p{p}",
                                "family": "P3_config_mirror",
                                "unlock": {
                                    "startDate": normal_date,
                                    "startHour": normal_hour,
                                    "windMs": w,
                                    "pitchAngle": p,
                                },
                                "config": {
                                    "startDate": d,
                                    "startHour": h,
                                    "pitchAngle": p,
                                    "turbineMode": default_mode(p),
                                },
                            }
                        )

        # Usuniecie duplikatow i limit.
        seen: set[str] = set()
        unique_cases: list[dict[str, Any]] = []
        for case in all_cases:
            key = json.dumps(case, sort_keys=True, ensure_ascii=False)
            if key in seen:
                continue
            seen.add(key)
            unique_cases.append(case)
            if len(unique_cases) >= max_cases:
                break
        return unique_cases

    def _append_live_trace(self, trace: dict[str, Any]) -> None:
        self._live_trace_path.parent.mkdir(parents=True, exist_ok=True)
        with self._live_trace_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(trace, ensure_ascii=False) + "\n")

    def _path(self, name: str) -> Path:
        return self._run_output_dir / name

    @staticmethod
    def _iso_now() -> str:
        return datetime.now().isoformat(timespec="milliseconds")
