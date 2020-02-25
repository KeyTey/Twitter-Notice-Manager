from flask import Flask, request, render_template
import os, json, datetime
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from requests_oauthlib import OAuth1Session

app = Flask(__name__)
CORS(app)

db_url = os.environ.get('DATABASE_URL') or "postgresql://localhost/notice"
app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

CK = os.environ['TWITTER_CONSUMER_KEY']
CS = os.environ['TWITTER_CONSUMER_SECRET']
AT = os.environ['TWITTER_ACCESS_TOKEN']
AS = os.environ['TWITTER_ACCESS_SECRET']
twitter = OAuth1Session(CK, CS, AT, AS)

ACCEPTED_IP = os.environ['ACCEPTED_IP']

# 通知テーブル
class Notice(db.Model):
    __tablename__ = 'notices'
    id = db.Column(db.Integer, primary_key = True)
    # 通知を受けたユーザー
    receiver_id = db.Column(db.String(), nullable = False)
    # 通知を送ったユーザー
    sender_id = db.Column(db.String(), nullable = False)
    # 通知対象のツイートID
    tweet_id = db.Column(db.String(), nullable = False)
    # 通知時間
    timestamp = db.Column(db.Integer, nullable = False)
    # データを辞書型として取得
    def get_dict(self):
        data = {
            'id': self.id,
            'receiver_id': self.receiver_id,
            'sender_id': self.sender_id,
            'tweet_id': self.tweet_id,
            'timestamp': self.timestamp
        }
        return data

# IPチェック
def accepted():
    return request.access_route[0] == ACCEPTED_IP

# タイムスタンプ取得
def get_timestamp(date):
    date = datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.000Z")
    date = date + datetime.timedelta(hours = 9)
    timestamp = int(date.timestamp())
    return timestamp

# 重複チェック
def exist(notice):
    count = db.session.query(Notice).filter(
        Notice.receiver_id == notice.receiver_id,
        Notice.sender_id == notice.sender_id,
        Notice.tweet_id == notice.tweet_id
    ).count()
    return count > 0

# ユーザーネームからユーザー取得
def get_user(name):
    url = "https://api.twitter.com/1.1/users/show.json"
    params = {
        'screen_name': name,
        'include_entities': False
    }
    res = twitter.get(url, params = params, timeout = 10)
    if res.status_code != 200: return {}
    return json.loads(res.text)

# IDリストからユーザーリスト取得
def get_users(user_ids):
    url = "https://api.twitter.com/1.1/users/lookup.json"
    params = {
        'user_id': ','.join(user_ids),
        'include_entities': False
    }
    res = twitter.get(url, params = params, timeout = 10)
    if res.status_code != 200: return []
    return json.loads(res.text)

# 通知追加
def add_notice(data):
    # パラメータ読み込み
    receiver = data.get('receiver')
    sender = data.get('sender')
    tweet_id = data.get('tweet_id')
    date = data.get('datetime')
    if not (receiver and sender and tweet_id and date): return {}
    # ユーザーネームからユーザーID取得
    receiver_id = get_user(receiver).get('id_str')
    sender_id = get_user(sender).get('id_str')
    if not (receiver_id and sender_id): return {}
    # 通知作成 -> 通知追加
    notice = Notice()
    notice.receiver_id = receiver_id
    notice.sender_id = sender_id
    notice.tweet_id = tweet_id
    notice.timestamp = get_timestamp(date)
    if exist(notice): return {}
    db.session.add(notice)
    db.session.commit()
    return notice.get_dict()

# 通知取得
def get_notices(size):
    notices = db.session.query(Notice).order_by(Notice.timestamp.desc()).limit(size).all()
    notices = [notice.get_dict() for notice in notices]
    return notices

# トップページ
@app.route('/')
def index():
    notices = get_notices(size = 100)
    user_ids = [user_id for notice in notices for user_id in [notice['receiver_id'], notice['sender_id']]]
    user_ids = list(set(user_ids))
    users = get_users(user_ids)
    users = {user['id_str']: user['screen_name'] for user in users}
    for notice in notices:
        notice['receiver'] = users[notice['receiver_id']]
        notice['sender'] = users[notice['sender_id']]
        notice['datetime'] = str(datetime.datetime.fromtimestamp(notice['timestamp']))
    return render_template('index.html', notices = notices)

# 通知取得API
# size: 通知取得数
@app.route('/notices', methods = ['GET'])
def api_get_notices():
    size = request.args.get('size', 10)
    notices = get_notices(size)
    return json.dumps(notices, indent = 4)

# 通知追加API
# receiver: 通知の受信ユーザー
# sender: 通知の送信ユーザー
# tweet_id: ツイートID
# datetime: タイムスタンプ
@app.route('/notice/create', methods = ['GET'])
def api_create_notice():
    if not accepted(): return {}
    notice = add_notice(request.args)
    return json.dumps(notice, indent = 4)

# 通知追加API
# receiver: 通知の受信ユーザー
# sender: 通知の送信ユーザー
# tweet_id: ツイートID
# datetime: タイムスタンプ
@app.route('/notice', methods = ['POST'])
def api_post_notice():
    if not accepted(): return {}
    notice = add_notice(request.get_json())
    return json.dumps(notice, indent = 4)

# 通知削除API
# id: 対象ID
@app.route('/notice', methods = ['DELETE'])
def api_delete_notice():
    if not accepted(): return {}
    req = request.get_json()
    data = db.session.query(Notice).filter(Notice.id == req['id']).first()
    if data is None: return {}
    notice = data.get_dict()
    db.session.delete(data)
    db.session.commit()
    return json.dumps(notice, indent = 4)

if __name__ == "__main__":
    app.run(host = '0.0.0.0', port = 8080, debug = True)
