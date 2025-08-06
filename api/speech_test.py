# api/speech_test.py (最終アーキテクチャ・.env対応版)

from fastapi import APIRouter, UploadFile, File
from google.cloud import speech
from google.oauth2 import service_account # 追加
import io
import os              # 追加
import json            # 追加
import base64          # 追加
from dotenv import load_dotenv # 追加

# .envファイルから環境変数をプログラムに読み込む
load_dotenv()

router = APIRouter()

# --- 認証情報の設定 ---
# .envファイルからBase64エンコードされた認証情報を取得
encoded_credentials = os.getenv("GOOGLE_CREDENTIALS_BASE64")

# もし.envファイルに設定がなければ、エラーを発生させてプログラムを停止
if not encoded_credentials:
    raise ValueError("環境変数 'GOOGLE_CREDENTIALS_BASE64' が.envファイルに設定されていません。")

# Base64文字列をデコードして、元のJSON形式に戻す
decoded_credentials = base64.b64decode(encoded_credentials)
credentials_info = json.loads(decoded_credentials)

# JSON情報から認証オブジェクトを作成
credentials = service_account.Credentials.from_service_account_info(credentials_info)

# 認証情報を明示的に指定して、Googleのクライアントを初期化
speech_client = speech.SpeechClient(credentials=credentials)
# --- 認証情報の設定ここまで ---


# WebSocketの代わりに、通常のHTTP POSTエンドポイントを用意
@router.post("/transcribe_audio")
async def transcribe_audio(audio_file: UploadFile = File(...)):
    print(f"[バックエンド] 音声ファイル '{audio_file.filename}' を受信しました。")

    # アップロードされた音声データをメモリ上で読み込む
    content = await audio_file.read()
    audio = speech.RecognitionAudio(content=content)

    # 成功が証明された、最も確実な設定
    config = speech.RecognitionConfig( # ← 正しい名前に修正
        encoding=speech.RecognitionConfig.AudioEncoding.WEBM_OPUS,
        language_code="ja-JP",
        enable_automatic_punctuation=True,
    )

    try:
        # ストリーミングではない、通常の認識APIを呼び出す
        response = speech_client.recognize(config=config, audio=audio)
        print("[バックエンド] Googleからの認識結果を受信しました。")

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