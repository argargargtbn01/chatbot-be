from flask import Flask, request, Response, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from flask_cors import CORS
import requests
import json

app = Flask(__name__)
CORS(app)

# Cấu hình cơ sở dữ liệu PostgreSQL
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:argargargtbn1@localhost:5432/chatbot'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Models cho SQLAlchemy
class Chat(db.Model):
    __tablename__ = 'chat'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Message(db.Model):
    __tablename__ = 'message'
    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.Integer, db.ForeignKey('chat.id'), nullable=False)
    sender = db.Column(db.String, nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

def generate_response_stream(user_input):
    api_url = "http://localhost:11434/api/generate"
    payload = {
        "model": "qwen2-math:1.5b-instruct",
        "prompt": user_input
    }
    try:
        with requests.post(api_url, json=payload, stream=True) as response:
            if response.status_code == 200:
                for chunk in response.iter_lines(decode_unicode=True):
                    if chunk:
                        yield chunk
            else:
                yield json.dumps({"error": response.text})
    except requests.exceptions.RequestException as e:
        yield json.dumps({"error": str(e)})

def get_or_create_chat(session_name):
    chat = Chat.query.filter_by(name=session_name).first()
    if not chat:
        chat = Chat(name=session_name)
        db.session.add(chat)
        db.session.commit()
    return chat

@app.route('/chat', methods=['POST'])
def chat():
    data = request.get_json()
    chat_id = data.get('chat_id')
    user_message = data.get('message')

    if not user_message:
        return jsonify({'error': 'No message provided'}), 400

    if not chat_id:
        session_name = user_message[:30]
        chat_session = get_or_create_chat(session_name)
        chat_id = chat_session.id
    else:
        chat_session = Chat.query.filter_by(id=chat_id).first()
        if not chat_session:
            return jsonify({'error': 'Invalid chat_id'}), 400

    user_msg = Message(chat_id=chat_id, sender="User", content=user_message)
    db.session.add(user_msg)
    db.session.commit()

    # Sử dụng response_generator để stream phản hồi
    def response_generator():
        complete_response = ""

        for chunk in generate_response_stream(user_message):

            try:
                parsed_chunk = json.loads(chunk)
                response_part = parsed_chunk.get("response", "")

                complete_response += response_part
                yield json.dumps({"response": response_part}) + "\n"

            except json.JSONDecodeError:
                yield json.dumps({"response": chunk}) + "\n"

        # Lưu phản hồi hoàn chỉnh vào database trong application context
        with app.app_context():
            bot_message = Message(chat_id=chat_id, sender="Bot", content=complete_response.strip())
            db.session.add(bot_message)
            db.session.commit()


    # Trả về Response từ hàm chat
    return Response(response_generator(), content_type='application/json')


@app.route('/chat-session', methods=['GET'])
def get_chat_sessions():
    chat_sessions = Chat.query.order_by(Chat.created_at.desc()).all()
    result = [{"chat_id": chat.id, "name": chat.name} for chat in chat_sessions]
    return jsonify(result)

@app.route('/message', methods=['GET'])
def get_messages():
    chat_id = request.args.get('chat_id')
    if not chat_id:
        return jsonify({'error': 'No chat_id provided'}), 400

    messages = Message.query.filter_by(chat_id=chat_id).order_by(Message.created_at.desc()).all()
    result = [{"sender": msg.sender, "content": msg.content, "created_at": msg.created_at.isoformat()} for msg in messages]
    return jsonify(result)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=4000)
