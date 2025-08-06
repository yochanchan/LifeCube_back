# final_test.py

import time
from google.cloud import speech

def run_final_test():
    print("診断プログラムを開始します...")
    
    # ステップ1で用意した音声ファイル名を指定
    audio_file_name = "test_audio.wav"

    try:
        # Google Speech-to-Textクライアントの初期化
        # これが失敗する場合、認証に問題があります
        client = speech.SpeechClient()
        print("1. Googleクライアントの初期化... OK")
    except Exception as e:
        print(f"1. Googleクライアントの初期化で致命的なエラー: {e}")
        return

    # 音声認識の設定 (WAVファイル用)
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=16000,
        language_code="ja-JP",
    )
    streaming_config = speech.StreamingRecognitionConfig(config=config)
    print("2. 音声認識設定の作成... OK")

    try:
        # 音声ファイルをバイナリモードで読み込む
        with open(audio_file_name, "rb") as audio_file:
            # チャンクに分けて読み込むための準備
            content = audio_file.read()
            # チャンクをストリームとして扱うためのジェネレータ
            def stream_generator(audio_content):
                chunk_size = 4096 # 4KBずつに分割
                for i in range(0, len(audio_content), chunk_size):
                    # データを少しずつyieldで送る
                    yield speech.StreamingRecognizeRequest(audio_content=audio_content[i:i + chunk_size])
                    print(f"  - 音声データのチャンクを送信中 ({i // chunk_size + 1}回目)...")
                    time.sleep(0.1) # 実際のストリーミングを模倣
            
            print("3. 音声ファイルのストリーミングを開始します...")
            requests = stream_generator(content)

            # streaming_recognize APIを呼び出し
            # ここでクラッシュする場合、gRPCライブラリに問題があります
            responses = client.streaming_recognize(
                config=streaming_config,
                requests=requests,
            )

            print("4. Googleからの応答を待っています...")
            # 応答を処理
            for response in responses:
                for result in response.results:
                    if result.is_final:
                        print("-" * 20)
                        print(f"最終認識結果: {result.alternatives[0].transcript}")
                        print("-" * 20)

        print("5. 診断プログラムが正常に完了しました！")

    except Exception as e:
        print("3,4のステップで致命的なエラーが発生しました。")
        print(f"  エラーの種類: {type(e).__name__}")
        print(f"  エラーメッセージ: {e}")

# プログラムの実行
if __name__ == "__main__":
    run_final_test()