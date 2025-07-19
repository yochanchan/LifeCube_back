## backend
cd backend

## （よ）pythonは3.11にする
py -3.11 -m venv env

env/Script/activate

pip install -r requirements.txt

uvicorn app:app --reload

## frontend

cd frontend

npm install

npm run dev

## 立ち上げ
http://localhost:3000/ にアクセス


## （よ）typescriptいれる
npm i -D typescript @types/react @types/react-dom @types/node



## （よ）frontend側の.envは下記2行のようにしておくと便利（##もそのまま使う。1行目と2行目を入れ替えて使うイメージ）
## NEXT_PUBLIC_API_ENDPOINT="https://app-002-gen10-step3-2-py-oshima10.azurewebsites.net"
NEXT_PUBLIC_API_ENDPOINT="http://127.0.0.1:8000"

