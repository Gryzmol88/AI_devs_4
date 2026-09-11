from fastapi import FastAPI
from pydantic import BaseModel

from .agent import run_agent
from .sessions import append_messages, get_messages

app = FastAPI()


class ChatRequest(BaseModel):
    sessionID: str
    msg: str


class ChatResponse(BaseModel):
    msg: str


def _short(text: str, limit: int = 240) -> str:
    compact = " ".join(text.split())
    return compact if len(compact) <= limit else f"{compact[:limit]}..."


@app.post("/", response_model=ChatResponse)
def chat(payload: ChatRequest) -> ChatResponse:
    try:
        print(f"[http] session={payload.sessionID} in={_short(payload.msg)}")
        # Dla danej sesji dopisujemy nowe pytanie operatora.
        append_messages(payload.sessionID, [{"role": "user", "content": payload.msg}])

        # Przekazujemy caly kontekst rozmowy do petli Function Calling.
        reply, new_messages = run_agent(get_messages(payload.sessionID), session_id=payload.sessionID)

        # Zapisujemy wszystkie kroki modelu (assistant/tool), aby utrzymac pamiec sesji.
        append_messages(payload.sessionID, new_messages)
        print(f"[http] session={payload.sessionID} out={_short(reply)}")
        return ChatResponse(msg=reply)
    except Exception as error:  # noqa: BLE001
        # Ostateczny bezpiecznik endpointu: nie zwracamy HTTP 500 do operatora.
        print(f"[main] unhandled_error={error}")
        return ChatResponse(msg="Wystapil chwilowy blad systemu. Sprobuj ponownie.")
