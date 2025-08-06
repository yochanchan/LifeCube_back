# api/speech_test.py (最終アーキテクチャ版)

from fastapi import APIRouter, UploadFile, File
from google.cloud import speech
import io

router = APIRouter()
speech_client = speech.SpeechClient()

# WebSocketの代わりに、通常のHTTP POSTエンドポイントを用意
@router.post("/transcribe_audio")
async def transcribe_audio(audio_file: UploadFile = File(...)):
    print(f"[バックエンド] 音声ファイル '{audio_file.filename}' を受信しました。")

    # アップロードされた音声データをメモリ上で読み込む
    content = await audio_file.read()
    audio = speech.RecognitionAudio(content=content)

    # final_test.pyで成功した、最も確実な設定
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.WEBM_OPUS,
        language_code="ja-JP",
        enable_automatic_punctuation=True,
    )

    try:
        # ストリーミングではない、通常の認識APIを呼び出す
        response = speech_client.recognize(config=config, audio=audio)
        print("[バックエンド] Googleからの認識結果を受信しました。")

        # 認識結果を結合して一つのテキストにする
        transcription = "".join(
            result.alternatives[0].transcript for result in response.results
        )

        if transcription:
            print(f"  -> 認識結果: {transcription}")
            return {"success": True, "transcription": transcription}
        else:
            print("  -> 認識結果が空でした。")
            return {"success": False, "transcription": ""}

    except Exception as e:
        print(f"[バックエンド] エラーが発生しました: {e}")
        return {"success": False, "transcription": "エラーが発生しました。"}