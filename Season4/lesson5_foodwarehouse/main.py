"""Entrypoint aplikacji rozwiązującej zadanie foodwarehouse."""

from pathlib import Path

from config import Settings
from api_client import ApiClient, ApiClientHttpError
from openrouter_client import OpenRouterClient
from services.db_discovery import DatabaseDiscoveryService
from services.signature_service import SignatureService
from services.warehouse_service import WarehouseService
from utils import logger
from utils.io import create_timestamped_output_dir, ensure_output_dir, write_json


def run() -> None:
    """Uruchamia pełny workflow zadania i zapisuje wynik końcowy.

    Returns:
        None

    Side Effects:
        Ładuje konfigurację, wysyła żądania do API i zapisuje pliki w katalogu output.
    """

    logger.info("Uruchamianie programu.")
    settings = Settings()
    logger.info("Załadowano konfigurację z Season4/.env.")
    logger.info(f"Wybrany model OpenRouter: {settings.openrouter_model}")

    base_output_dir = ensure_output_dir(
        (Path(__file__).resolve().parent / settings.output_dir).resolve()
    )
    output_dir = create_timestamped_output_dir(base_output_dir)
    logger.info(f"Katalog wynikowy run: {output_dir}")

    api_client = ApiClient(settings)
    openrouter_client = OpenRouterClient(settings)
    db_service = DatabaseDiscoveryService(api_client)
    signature_service = SignatureService(api_client)
    warehouse_service = WarehouseService(
        settings=settings,
        api_client=api_client,
        db_service=db_service,
        signature_service=signature_service,
        openrouter_client=openrouter_client,
        output_dir=output_dir,
    )

    try:
        warehouse_service.save_agent_hint()
        logger.info("Zapisano podpowiedź SQL od agenta OpenRouter.")
        final_response = warehouse_service.run()
        write_json(output_dir / "final_response.json", final_response)
        logger.info("Zakończono sukcesem.")
    except ApiClientHttpError as exc:
        write_json(
            output_dir / "step_error_http.json",
            {
                "status_code": exc.status_code,
                "reason": exc.reason,
                "body": exc.body,
                "url": exc.url,
                "payload": exc.payload,
            },
        )
        logger.error(f"Błąd HTTP API: {exc.status_code} {exc.reason}")
        raise
    except Exception as exc:
        logger.error(f"Błąd krytyczny: {exc}")
        raise


if __name__ == "__main__":
    run()
