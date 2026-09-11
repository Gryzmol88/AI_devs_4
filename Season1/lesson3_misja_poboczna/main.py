from fastapi import FastAPI
from pydantic import BaseModel

from .agent import run_agent
from .config import HAS_HUB_KEY, HAS_OPENROUTER_KEY, LOADED_DOTENV_FILES
from .sessions import append_messages, get_messages

app = FastAPI(title="lesson3_misja_poboczna")


class ChatRequest(BaseModel):
    sessionID: str
    msg: str


class ChatResponse(BaseModel):
    msg: str


@app.on_event("startup")
def startup_info() -> None:
    loaded = ", ".join(LOADED_DOTENV_FILES) if LOADED_DOTENV_FILES else "(none)"
    print(f"[config] dotenv_loaded={loaded}")
    print(f"[config] OPENROUTER_API_KEY_set={HAS_OPENROUTER_KEY} HUB_API_KEY_set={HAS_HUB_KEY}")


@app.post("/", response_model=ChatResponse)
def chat(payload: ChatRequest) -> ChatResponse:
    append_messages(payload.sessionID, [{"role": "user", "content": payload.msg}])
    reply, new_messages = run_agent(get_messages(payload.sessionID))
    append_messages(payload.sessionID, new_messages)
    return ChatResponse(msg=reply)
