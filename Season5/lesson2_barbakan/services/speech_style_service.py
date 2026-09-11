"""Stylizuje wypowiedzi agenta tak, aby brzmialy naturalnie."""

from clients.openrouter_client import OpenRouterClient
from models import DialogState


class SpeechStyleService:
    """Przygotowuje naturalne, krotkie wypowiedzi do syntezy mowy.

    Args:
        client: Klient OpenRouter wykorzystywany do generowania tekstu.
    """

    def __init__(self, client: OpenRouterClient) -> None:
        """Inicjalizuje serwis stylu wypowiedzi."""

        self._client = client

    def humanize(
        self,
        base_text: str,
        state: DialogState,
        inbound_text: str,
        conversation_history: str,
    ) -> str:
        """Przepisuje tekst na bardziej naturalna wersje.

        Args:
            base_text: Bazowa tresc wypowiedzi.
            state: Aktualny stan dialogu.
            inbound_text: Ostatnia wypowiedz operatora z centrali.
            conversation_history: Pelny transkrypt rozmowy do biezacego kroku.

        Returns:
            str: Krotka, naturalna wypowiedz po polsku.
        """
        system_prompt = (
            "Tworzysz pojedyncza kwestie do rozmowy telefonicznej po polsku. "
            "Twoja tozsamosc jest stala: jestes Tymon Gajewski i nie wolno jej zmieniac. "
            "Nigdy nie podawaj innego imienia ani nazwiska, nie udawaj innej osoby. "
            "Brzmij naturalnie, po ludzku i kolezensko, jak normalna rozmowa. "
            "Unikaj tonu urzedowego, handlowego i call-center. "
            "Mow krotko i zwyczajnie, bez oficjalnych formul i bez korpomowy. "
            "Nie prowadz zbednego small talku i nie dodawaj pustych wstawek. "
            "Nie uzywaj slowa 'cześć'. "
            "Uzywaj poprawnej polszczyzny i polskich znakow. "
            "Zachowaj sens, intencje i wszystkie kluczowe dane (np. RD224, BARBAKAN). "
            "Wynik: jedno zdanie, maksymalnie 12 slow, bez cudzyslowow i bez wykrzyknikow. "
            "Regula stanu intro: tylko przywitanie i przedstawienie sie, bez prosb i bez pytan o drogi. "
            "Po pierwszym przedstawieniu sie nie witaj sie ponownie i nie przedstawiaj sie drugi raz. "
            "Regula stanu ask_roads: jesli operator pyta o potrzeby, najpierw krotko odpowiedz, "
            "a potem zapytaj o status tras RD."
        )
        user_prompt = (
            f"Stan rozmowy: {state.value}\n"
            f"Ostatnia wypowiedz operatora: {inbound_text or '(brak)'}\n"
            f"Pelny transkrypt rozmowy:\n{conversation_history or '(brak)'}\n"
            f"Tekst bazowy: {base_text}\n"
            "Odpowiedz naturalnie i po ludzku, reagujac na wypowiedz operatora."
        )
        rewritten = self._client.generate_reply(system_prompt, user_prompt).strip()
        if not rewritten:
            return base_text.strip()
        return rewritten
