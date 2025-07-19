from enum import Enum
from io import BytesIO
from textwrap import dedent
from typing import List

from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from openai import OpenAI, OpenAIError
from pydantic import BaseModel, Field

load_dotenv()

# --------------------------- データモデル --------------------------- #
class Seat(str, Enum):
    DRIVER = "DRIVER"
    FRONT_PASSENGER = "FRONT_PASSENGER"
    REAR_LEFT = "REAR_LEFT"
    REAR_RIGHT = "REAR_RIGHT"

    @property
    def jp(self) -> str:
        return {
            "DRIVER": "運転手",
            "FRONT_PASSENGER": "助手席",
            "REAR_LEFT": "後部左",
            "REAR_RIGHT": "後部右",
        }[self.value]


class Passenger(BaseModel):
    seat: Seat
    name: str
    age: int
    gender: str
    likes_pretend_play: bool
    role: str


class PlayRequest(BaseModel):
    scenario: str
    destination: str
    ride_time: int = Field(..., gt=0)
    passengers: List[Passenger]


class TTSRequest(BaseModel):
    partial_narration: str = Field(..., max_length=4096)  # TTS 文字数上限 :contentReference[oaicite:6]{index=6}


router = APIRouter(prefix="/api", tags=["role_play"])


# ------------- ヘルパー：クライアント生成（毎リクエスト） ------------- #
def get_client() -> OpenAI:
    """スレッドセーフ確保のため、都度生成する軽量クライアント"""
    return OpenAI()  # api_key / org は環境変数参照


# ------------------------- ナレーション生成 ------------------------- #
@router.post("/play")
async def create_role_play_narration(req: PlayRequest):
    try:
        driver_name = next(p.name for p in req.passengers if p.seat == Seat.DRIVER)
    except StopIteration:
        raise HTTPException(status_code=422, detail="運転手がいません")

    passenger_block = "\n".join(
        f"・{p.name}：{p.seat.jp}、{p.age}歳、{p.gender}、"
        f"「ごっこ遊び」は{'とても好き' if p.likes_pretend_play else 'あまり好きではない'}"
        for p in req.passengers
    )

    prompt = dedent(
        f"""
        子ども用の「ごっこ遊び」のナレーション音声用の文章を作成してください。
        ・最初に、登場人物に役割を与えます。一緒に遊ぶ大人にも役割を与えます。
        ・次に、導入用のナレーションを行います。その際、誰がどの役を担当するのか、分かるように伝えてください。また、主役となる子どもたちに話しかける形でスタートするようにしてください。
        ・その後、想定される「ごっこ遊び」の会話シーンを挿入します。このパートはナレーションではありません。
        ・最後に、目的地に着いたときの締め用のナレーションを行います。

        【注意事項】
        ・子どもたちに主役を与えてください。
        ・車内で遊ぶので、{driver_name}には、あまりセリフのない脇役を与えてください。
        ・子どもが理解できるようなナレーションにしてください。

        【シナリオ】
        ・{req.scenario}

        【目的地】
        ・{req.destination}

        【乗車時間】
        ・{req.ride_time}分

        【ユーザー（呼び名）】
        {passenger_block}
        """
    ).strip()

    client = get_client()
    try:
        completion = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
            max_tokens=800,  # コスト最適化
        )
        narration = completion.choices[0].message.content
    except OpenAIError as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"prompt": prompt, "narration": narration}


# --------------------------- TTS エンドポイント --------------------------- #
@router.post("/tts")
async def text_to_speech(req: TTSRequest):
    client = get_client()
    try:
        response = client.audio.speech.create(
            model="tts-1",
            voice="nova",
            input=req.partial_narration,
            response_format="mp3",
        )
        audio_bytes: bytes = response.content  # 正しい属性
    except OpenAIError as e:
        raise HTTPException(status_code=500, detail=str(e))

    return StreamingResponse(
        BytesIO(audio_bytes),
        media_type="audio/mpeg",
        headers={"Content-Disposition": "inline; filename=narration.mp3"},
    )
