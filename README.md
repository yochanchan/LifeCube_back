# Step3-1　宿題パッケージstarterのサンプルアプリです

## クローン
git clone https://github.com/techzerocs/LinkFastAPINext_starter.git


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